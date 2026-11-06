"""Обёртка над Ollama API для всех LLM-вызовов проекта.

Используется и из candidates/tasks.py (коррекция, структуризация, embedding),
и из vacancies/ (извлечение требований вакансии, объяснение матча) —
единая точка вызова, чтобы не дублировать обращение к LLM в двух Django apps
(см. карточку "common" в Obsidian).

Критично: модель — ТОЛЬКО "qwen3-30b-a3b-fixed" (см. "LLM-модель (Qwen)" —
у базового тега qwen3:30b-a3b сломан шаблон чата, think:false не работает).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / 'prompts'

# Под конкурентной нагрузкой (несколько воркеров Django-Q2 бьют в одну Ollama
# одновременно) генерация заметно замедляется — 180с оказалось мало.
CHAT_TIMEOUT = 480
# Было 60с — под конкурентной нагрузкой (2 воркера бьют в одну Ollama) даже
# лёгкий embedding-вызов может встать в очередь позади тяжёлой генерации.
EMBED_TIMEOUT = 180


class LLMError(Exception):
    """Ollama вернул ошибку, не-JSON где ожидался JSON, или не done_reason=stop."""


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding='utf-8')


def _render(template: str, **kwargs: object) -> str:
    """Подстановка плейсхолдеров вида {name}. Не str.format() — промпты
    содержат JSON-схемы с литеральными { } в примерах, format() на них упал бы.
    """
    for key, value in kwargs.items():
        template = template.replace('{' + key + '}', str(value))
    return template


def _chat(prompt: str, *, json_mode: bool = False) -> str:
    url = f'{settings.OLLAMA_BASE_URL}/api/chat'
    payload = {
        'model': settings.OLLAMA_LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'think': False,
        'stream': False,
    }
    if json_mode:
        payload['format'] = 'json'

    response = requests.post(url, json=payload, timeout=CHAT_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    done_reason = data.get('done_reason')
    if done_reason != 'stop':
        logger.warning('Ollama done_reason=%s (ожидался "stop"), модель=%s', done_reason, settings.OLLAMA_LLM_MODEL)

    content = data.get('message', {}).get('content', '')
    return content.strip()


def _parse_json(text: str) -> dict:
    # На случай если модель всё же обернёт ответ в ```json ... ``` несмотря на инструкцию в промпте
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        if cleaned.startswith('json'):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f'Ollama вернул невалидный JSON: {exc}\n--- ответ ---\n{text}') from exc


def _looks_like_leaked_reasoning(raw_text: str, corrected_text: str) -> bool:
    """Обнаруженный на практике баг: на некоторых входах (замечено на azərbaycan dili
    без диакритики) модель выводит рассуждения вслух как обычный текст контента, а
    не в <think>, несмотря на think:false и done_reason=stop (т.е. это не обрыв по
    таймауту/лимиту токенов — модель сама решает закончить после "рассуждения").
    Эвристика: честная коррекция не может быть в разы длиннее оригинала.
    """
    return len(corrected_text) > 3 * len(raw_text) + 200


def correct_cv_text(raw_text: str) -> str:
    """correction_prompt.md — исправление орфографии/грамматики CV, язык не меняется.

    Один retry при подозрении на утечку рассуждений в контент (см.
    _looks_like_leaked_reasoning), иначе fallback на raw_text — лучше отдать
    в структуризацию неисправленный, но настоящий текст CV, чем "рассуждения вслух".
    """
    prompt = _render(_load_prompt('correction_prompt.md'), raw_text=raw_text)

    corrected = _chat(prompt)
    if not _looks_like_leaked_reasoning(raw_text, corrected):
        return corrected

    logger.warning('Похоже на утечку рассуждений в ответ коррекции, повторяю попытку')
    corrected_retry = _chat(prompt)
    if not _looks_like_leaked_reasoning(raw_text, corrected_retry):
        return corrected_retry

    logger.error('Коррекция дважды вернула аномально длинный ответ, использую raw_text без коррекции')
    return raw_text


def structure_cv(corrected_text: str) -> dict:
    """structuring_prompt.md — структуризация CV в JSON-схему Candidate."""
    prompt = _render(_load_prompt('structuring_prompt.md'), corrected_text=corrected_text)
    raw = _chat(prompt, json_mode=True)
    return _parse_json(raw)


def extract_vacancy_requirements(vacancy_text: str) -> dict:
    """vacancy_requirements_prompt.md — извлечение требований из текста вакансии."""
    prompt = _render(_load_prompt('vacancy_requirements_prompt.md'), vacancy_text=vacancy_text)
    raw = _chat(prompt, json_mode=True)
    return _parse_json(raw)


def explain_match(
    candidate_json: dict,
    vacancy_json: dict,
    *,
    semantic_similarity: float,
    skill_overlap: float,
    experience_score: float,
    passed_hard_filters: bool,
) -> str:
    """match_explanation_prompt.md — текстовое объяснение готового скора (не пересчитывает его)."""
    prompt = _render(
        _load_prompt('match_explanation_prompt.md'),
        candidate_json=json.dumps(candidate_json, ensure_ascii=False),
        vacancy_json=json.dumps(vacancy_json, ensure_ascii=False),
        semantic_similarity=semantic_similarity,
        skill_overlap=skill_overlap,
        experience_score=experience_score,
        passed_hard_filters=passed_hard_filters,
    )
    return _chat(prompt)


def judge_search_match(candidate_json: dict, query_text: str) -> dict:
    """ai_search_explanation_prompt.md — решает is_match (строго) + объяснение для
    свободного AI-поиска по базе (candidates/search.py). Возвращает dict
    {"is_match": bool, "explanation": str}.
    """
    prompt = _render(
        _load_prompt('ai_search_explanation_prompt.md'),
        candidate_json=json.dumps(candidate_json, ensure_ascii=False),
        query_text=query_text,
    )
    raw = _chat(prompt, json_mode=True)
    return _parse_json(raw)


def get_embedding(text: str) -> list[float]:
    """Вектор эмбеддинга через nomic-embed-text (768 измерений)."""
    url = f'{settings.OLLAMA_BASE_URL}/api/embed'
    payload = {'model': settings.OLLAMA_EMBED_MODEL, 'input': text}
    response = requests.post(url, json=payload, timeout=EMBED_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    embeddings = data.get('embeddings')
    if not embeddings:
        raise LLMError(f'Ollama не вернул embeddings: {data}')
    return embeddings[0]

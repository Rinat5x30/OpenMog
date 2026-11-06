"""Фоновый пайплайн обработки CV — выполняется воркером Django-Q2.

Цепочка (см. "Фоновая обработка CV" в Obsidian):
1. парсинг файла -> сырой текст
2. определение языка (ru/az/en)
3. LLM: исправление орфографии/грамматики
4. LLM: структуризация в JSON-схему Candidate
5. embedding-вектор из структурированного профиля
-> запись в БД, processing_status='done' (или 'error' при сбое)
"""

from __future__ import annotations

import logging

import requests
from django.db import transaction

from common import llm_client
from common.llm_client import LLMError

from . import parsing
from .language import detect_language
from .models import Candidate
from .parsing import UnsupportedFileType

logger = logging.getLogger(__name__)


def _build_embedding_text(structured: dict) -> str:
    """Текст для вектора: сжатая суть профиля, а не весь сырой CV целиком."""
    parts = [
        structured.get('desired_position') or '',
        structured.get('summary') or '',
        ', '.join(structured.get('skills') or []),
    ]
    for exp in structured.get('experience') or []:
        parts.append(f"{exp.get('position', '')} {exp.get('responsibilities', '')}")
    return '\n'.join(p for p in parts if p).strip()


def process_candidate_cv(candidate_id: int) -> None:
    candidate = Candidate.objects.get(pk=candidate_id)
    candidate.processing_status = 'processing'
    candidate.save(update_fields=['processing_status'])

    try:
        raw_text = parsing.parse_cv_file(candidate.source_file.path)
        if not raw_text:
            raise ValueError('Не удалось извлечь текст из файла (пустой результат парсинга)')

        language_detected = detect_language(raw_text)
        corrected_text = llm_client.correct_cv_text(raw_text)
        structured = llm_client.structure_cv(corrected_text)

        contacts = structured.get('contacts') or {}
        embedding_text = _build_embedding_text(structured)
        embedding = llm_client.get_embedding(embedding_text) if embedding_text else None

        with transaction.atomic():
            candidate.raw_text = raw_text
            candidate.corrected_text = corrected_text
            candidate.language_detected = language_detected

            candidate.full_name = structured.get('full_name') or candidate.full_name
            candidate.phone = contacts.get('phone')
            candidate.email = contacts.get('email')
            candidate.telegram = contacts.get('telegram')
            candidate.linkedin = contacts.get('linkedin')
            candidate.location = structured.get('location')
            candidate.willing_to_relocate = structured.get('willing_to_relocate')
            desired_position = structured.get('desired_position')
            if not desired_position:
                # Найденная на практике непоследовательность модели: заголовок резюме
                # иногда не маппится в desired_position, даже когда он идентичен
                # position из experience[0]. Fallback — последняя/текущая должность.
                experience_list = structured.get('experience') or []
                if experience_list:
                    desired_position = experience_list[0].get('position') or None
            candidate.desired_position = desired_position
            # total_experience_years берётся как посчитала LLM — известный открытый риск
            # (неточность на датах), см. карточку "ТЗ" -> "Известные открытые риски"
            candidate.total_experience_years = structured.get('total_experience_years')
            candidate.experience = structured.get('experience') or []
            candidate.education = structured.get('education') or []
            candidate.skills = structured.get('skills') or []
            candidate.languages = structured.get('languages') or []
            candidate.summary = structured.get('summary') or ''
            candidate.embedding = embedding

            candidate.processing_status = 'done'
            candidate.save()

        logger.info('CV кандидата #%s обработан успешно', candidate_id)

    except (
        UnsupportedFileType, LLMError, ValueError, FileNotFoundError,
        requests.exceptions.RequestException,
    ) as exc:
        # requests.exceptions.RequestException (таймауты/обрывы к Ollama) —
        # найденный на практике баг: без этого кандидат застревал в
        # processing_status='processing' навечно, без записи ошибки.
        logger.exception('Ошибка обработки CV кандидата #%s', candidate_id)
        candidate.processing_status = 'error'
        candidate.hr_notes = (candidate.hr_notes or '') + f'\n[обработка не удалась: {exc}]'
        candidate.save(update_fields=['processing_status', 'hr_notes'])

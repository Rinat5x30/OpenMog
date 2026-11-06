"""AI-поиск по базе кандидатов на естественном языке: HR вводит запрос свободным
текстом ("хочу full-stack разработчиков с опытом 3+ года"), система ищет
семантически близких кандидатов через pgvector, затем LLM СТРОГО решает,
действительно ли кандидат подходит (is_match) — иначе кандидат не показывается
(см. ai_search_explanation_prompt.md: embedding-близость сама по себе не
гарантия релевантности, модель склонна рационализировать "совпадение" даже
для явно не подходящих профессий, поэтому решение явное и бинарное).

В отличие от vacancies/matching.py (формальная вакансия с гейтами must-have),
здесь нет жёстких фильтров по навыкам — это быстрый разведочный поиск по базе.
"""

from __future__ import annotations

from pgvector.django import CosineDistance

from common import llm_client

from .models import Candidate

# Сколько кандидатов берём из векторного поиска и реально прогоняем через
# LLM-судью. Каждый — отдельный LLM-вызов (~15-20с), поэтому не задираем
# слишком высоко — иначе AI-поиск становится неинтерактивным.
CANDIDATES_TO_JUDGE = 6


def _candidate_to_dict(candidate: Candidate) -> dict:
    return {
        'full_name': candidate.full_name,
        'desired_position': candidate.desired_position,
        'total_experience_years': candidate.total_experience_years,
        'skills': candidate.skills,
        'languages': candidate.languages,
        'summary': candidate.summary,
    }


def search_candidates(query_text: str) -> list[dict]:
    """Возвращает список {candidate, similarity, explanation} только для тех
    кандидатов, которых LLM-судья явно признал релевантными (is_match=true).
    """
    query_embedding = llm_client.get_embedding(query_text)

    candidates = (
        Candidate.objects
        .filter(processing_status='done', embedding__isnull=False)
        .annotate(cosine_distance=CosineDistance('embedding', query_embedding))
        .order_by('cosine_distance')[:CANDIDATES_TO_JUDGE]
    )

    results = []
    for candidate in candidates:
        similarity = max(0.0, min(1.0, 1.0 - candidate.cosine_distance))
        verdict = llm_client.judge_search_match(_candidate_to_dict(candidate), query_text)
        if not verdict.get('is_match'):
            continue
        results.append({
            'candidate': candidate,
            'similarity': similarity,
            'explanation': verdict.get('explanation', ''),
        })

    results.sort(key=lambda item: item['similarity'], reverse=True)
    return results

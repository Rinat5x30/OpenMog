"""Подбор и ранжирование кандидатов под вакансию (см. "Матчинг под вакансию",
"MatchResult" в Obsidian).

Шаг 1 — жёсткие фильтры (гейт, не score): must-have навыки и языковой минимум.
Шаг 2 — взвешенный score (считается всегда, даже для не прошедших гейт):

    final_score = 0.40 * semantic_similarity_score
                + 0.35 * skill_overlap_score
                + 0.15 * experience_score
                + 0.10 * education_score

Шаг 3 (опционально, только для top-K) — LLM-объяснение через match_explanation_prompt.md.
"""

from __future__ import annotations

from pgvector.django import CosineDistance

from candidates.models import Candidate
from common import llm_client

from .models import MatchResult, Vacancy

TOP_N_SEMANTIC = 50  # сколько кандидатов берём из векторного поиска перед пересчётом score
DEFAULT_EXPLAIN_TOP_K = 5

LANGUAGE_LEVELS = {'basic': 0, 'intermediate': 1, 'fluent': 2, 'native': 3}
EDUCATION_LEVELS = {'none': 0, 'secondary': 1, 'bachelor': 2, 'master': 3, 'phd': 4}

# Сопоставление свободного текста degree (RU/AZ/EN) с уровнем образования.
# Точного справочника нет ни в одном промпте — эвристика по ключевым словам.
_DEGREE_KEYWORDS = {
    'phd': ['phd', 'доктор', 'кандидат наук'],
    'master': ['магистр', 'master', 'magistr'],
    'bachelor': ['бакалавр', 'bachelor', 'bakalavr'],
    'secondary': ['средн', 'school', 'orta', 'secondary', 'school'],
}


def _normalize_skill(skill: str) -> str:
    return skill.strip().lower()


def _degree_to_level(degree: str | None) -> str:
    if not degree:
        return 'none'
    text = degree.lower()
    for level, keywords in _DEGREE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return level
    return 'none'


def _highest_education_level(education: list[dict]) -> str:
    levels = [_degree_to_level(entry.get('degree')) for entry in education or []]
    if not levels:
        return 'none'
    return max(levels, key=lambda level: EDUCATION_LEVELS.get(level, 0))


def check_hard_filters(candidate: Candidate, vacancy: Vacancy) -> tuple[bool, list[str]]:
    """Возвращает (passed, missing) — missing содержит непройденные must-have навыки
    и, дополнительно к схеме в карточке MatchResult, непройденные языковые минимумы
    (у модели нет отдельного поля под это — см. обновление карточки MatchResult).
    """
    candidate_skills = {_normalize_skill(s) for s in candidate.skills or []}
    missing = [
        skill for skill in (vacancy.must_have_skills or [])
        if _normalize_skill(skill) not in candidate_skills
    ]

    candidate_langs = {
        (lang.get('language') or '').strip().lower(): lang.get('level')
        for lang in candidate.languages or []
    }
    for requirement in vacancy.required_languages or []:
        lang_name = (requirement.get('language') or '').strip().lower()
        min_level = requirement.get('min_level')
        candidate_level = candidate_langs.get(lang_name)
        if LANGUAGE_LEVELS.get(candidate_level, -1) < LANGUAGE_LEVELS.get(min_level, 0):
            missing.append(f"язык: {requirement.get('language')} (нужен {min_level})")

    return (len(missing) == 0), missing


def compute_skill_overlap(candidate: Candidate, vacancy: Vacancy) -> float:
    nice_to_have = vacancy.nice_to_have_skills or []
    if not nice_to_have:
        # отсутствие необязательных пожеланий не должно наказывать кандидата
        return 1.0
    candidate_skills = {_normalize_skill(s) for s in candidate.skills or []}
    matched = sum(1 for skill in nice_to_have if _normalize_skill(skill) in candidate_skills)
    return matched / len(nice_to_have)


def compute_experience_score(candidate: Candidate, vacancy: Vacancy) -> float:
    if not vacancy.min_experience_years:
        return 1.0
    candidate_years = candidate.total_experience_years or 0.0
    return min(candidate_years / vacancy.min_experience_years, 1.0)


def compute_education_score(candidate: Candidate, vacancy: Vacancy) -> float:
    if not vacancy.required_education_level or vacancy.required_education_level == 'none':
        return 1.0
    candidate_level = _highest_education_level(candidate.education)
    if EDUCATION_LEVELS.get(candidate_level, 0) >= EDUCATION_LEVELS.get(vacancy.required_education_level, 0):
        return 1.0
    return 0.5  # образование почти никогда не единственная причина отказа


def _candidate_to_dict(candidate: Candidate) -> dict:
    return {
        'full_name': candidate.full_name,
        'desired_position': candidate.desired_position,
        'total_experience_years': candidate.total_experience_years,
        'skills': candidate.skills,
        'languages': candidate.languages,
        'education': candidate.education,
        'summary': candidate.summary,
    }


def _vacancy_to_dict(vacancy: Vacancy) -> dict:
    return {
        'title': vacancy.title,
        'must_have_skills': vacancy.must_have_skills,
        'nice_to_have_skills': vacancy.nice_to_have_skills,
        'min_experience_years': vacancy.min_experience_years,
        'required_education_level': vacancy.required_education_level,
        'required_languages': vacancy.required_languages,
        'seniority': vacancy.seniority,
    }


def score_candidate(candidate: Candidate, vacancy: Vacancy, *, cosine_distance: float) -> MatchResult:
    semantic_similarity_score = max(0.0, min(1.0, 1.0 - cosine_distance))
    passed_hard_filters, missing_must_have = check_hard_filters(candidate, vacancy)
    skill_overlap_score = compute_skill_overlap(candidate, vacancy)
    experience_score = compute_experience_score(candidate, vacancy)
    education_score = compute_education_score(candidate, vacancy)

    final_score = (
        0.40 * semantic_similarity_score
        + 0.35 * skill_overlap_score
        + 0.15 * experience_score
        + 0.10 * education_score
    )

    result, _ = MatchResult.objects.update_or_create(
        candidate=candidate,
        vacancy=vacancy,
        defaults={
            'semantic_similarity_score': semantic_similarity_score,
            'skill_overlap_score': skill_overlap_score,
            'experience_score': experience_score,
            'education_score': education_score,
            'passed_hard_filters': passed_hard_filters,
            'missing_must_have': missing_must_have,
            'final_score': final_score,
        },
    )
    return result


def attach_explanation(result: MatchResult) -> None:
    explanation = llm_client.explain_match(
        _candidate_to_dict(result.candidate),
        _vacancy_to_dict(result.vacancy),
        semantic_similarity=round(result.semantic_similarity_score, 2),
        skill_overlap=round(result.skill_overlap_score, 2),
        experience_score=round(result.experience_score, 2),
        passed_hard_filters=result.passed_hard_filters,
    )
    result.explanation_text = explanation
    result.save(update_fields=['explanation_text'])


def run_matching(vacancy: Vacancy, *, explain_top_k: int = DEFAULT_EXPLAIN_TOP_K) -> list[MatchResult]:
    """Полный цикл матчинга: векторный поиск top-N -> score для каждого -> explain для top-K."""
    candidates = (
        Candidate.objects
        .filter(processing_status='done', embedding__isnull=False)
        .annotate(cosine_distance=CosineDistance('embedding', vacancy.embedding))
        .order_by('cosine_distance')[:TOP_N_SEMANTIC]
    )

    results = [
        score_candidate(candidate, vacancy, cosine_distance=candidate.cosine_distance)
        for candidate in candidates
    ]
    results.sort(key=lambda r: (not r.passed_hard_filters, -r.final_score))

    for result in results[:explain_top_k]:
        attach_explanation(result)

    return results

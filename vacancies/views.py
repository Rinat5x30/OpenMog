"""Views vacancies: создание вакансии, запуск матчинга, результаты матчинга
(см. "Создание вакансии", "Матчинг под вакансию", "Результаты матчинга" в Obsidian).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from common import llm_client
from common.llm_client import LLMError

from .matching import run_matching
from .models import Vacancy


@login_required
def vacancy_list(request):
    vacancies = Vacancy.objects.all()
    return render(request, 'vacancies/list.html', {'vacancies': vacancies})


@login_required
def vacancy_create(request):
    """HR вводит текст вакансии свободным текстом; LLM извлекает структурированные
    требования синхронно (один быстрый вызов, ~10-20 сек — приемлемо для одного запроса).
    """
    if request.method == 'POST':
        title_hint = request.POST.get('title', '').strip()
        raw_description = request.POST.get('raw_description', '').strip()
        if not raw_description:
            messages.error(request, 'Please enter the vacancy description.')
            return redirect('vacancies:create')

        try:
            requirements = llm_client.extract_vacancy_requirements(raw_description)
        except LLMError as exc:
            messages.error(request, f'Could not parse the vacancy: {exc}')
            return redirect('vacancies:create')

        vacancy = Vacancy.objects.create(
            title=requirements.get('title') or title_hint or 'Untitled',
            raw_description=raw_description,
            must_have_skills=requirements.get('must_have_skills') or [],
            nice_to_have_skills=requirements.get('nice_to_have_skills') or [],
            min_experience_years=requirements.get('min_experience_years'),
            required_education_level=requirements.get('required_education_level'),
            required_languages=requirements.get('required_languages') or [],
            seniority=requirements.get('seniority'),
        )
        embedding_text = '\n'.join(filter(None, [
            vacancy.title,
            ', '.join(vacancy.must_have_skills),
            ', '.join(vacancy.nice_to_have_skills),
            raw_description,
        ]))
        vacancy.embedding = llm_client.get_embedding(embedding_text)
        vacancy.save(update_fields=['embedding'])

        messages.success(request, 'Vacancy created, requirements extracted.')
        return redirect('vacancies:detail', pk=vacancy.pk)

    return render(request, 'vacancies/create.html')


@login_required
def vacancy_detail(request, pk):
    vacancy = get_object_or_404(Vacancy, pk=pk)
    return render(request, 'vacancies/detail.html', {'vacancy': vacancy})


@login_required
def vacancy_run_match(request, pk):
    """Запускает подбор кандидатов синхронно (векторный поиск + score для всех,
    LLM-объяснение только для top-K — см. vacancies/matching.py).
    """
    vacancy = get_object_or_404(Vacancy, pk=pk)
    if request.method == 'POST':
        run_matching(vacancy)
        messages.success(request, 'Matching completed.')
    return redirect('vacancies:results', pk=pk)


@login_required
def vacancy_results(request, pk):
    vacancy = get_object_or_404(Vacancy, pk=pk)
    results = vacancy.match_results.select_related('candidate').order_by('-passed_hard_filters', '-final_score')
    return render(request, 'vacancies/results.html', {'vacancy': vacancy, 'results': results})

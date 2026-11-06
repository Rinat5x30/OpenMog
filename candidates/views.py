"""Views candidates: загрузка CV, карточка кандидата, работа с базой напрямую
(см. "Загрузка CV", "Карточка кандидата", "Работа с базой напрямую" в Obsidian).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django_q.tasks import async_task

from . import search as ai_search_module
from .models import HR_STATUS_CHOICES, Candidate

SORT_OPTIONS = {
    'created_desc': ('-created_at', 'Newest first'),
    'experience_desc': ('-total_experience_years', 'Most experience'),
    'name_asc': ('full_name', 'Name (A-Z)'),
}


@login_required
def candidate_list(request):
    """Поиск и фильтрация по базе кандидатов без привязки к вакансии (CRUD, без AI)."""
    candidates = Candidate.objects.all()

    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()
    hr_status = request.GET.get('hr_status', '').strip()
    skill = request.GET.get('skill', '').strip()
    language = request.GET.get('language', '').strip()
    min_experience = request.GET.get('min_experience', '').strip()
    sort = request.GET.get('sort', 'created_desc').strip()
    if sort not in SORT_OPTIONS:
        sort = 'created_desc'

    candidates = candidates.order_by(SORT_OPTIONS[sort][0])

    if query:
        candidates = candidates.filter(
            Q(full_name__icontains=query)
            | Q(desired_position__icontains=query)
            | Q(phone__icontains=query)
            | Q(email__icontains=query)
        )
    if location:
        candidates = candidates.filter(location__icontains=location)
    if hr_status:
        candidates = candidates.filter(hr_status=hr_status)

    candidates = list(candidates)

    # ArrayField/JSONField: фильтрация по подстроке элемента делается в Python —
    # для масштаба хакатона датасет небольшой, точный __contains на DB-уровне избыточен.
    if skill:
        skill_lower = skill.lower()
        candidates = [c for c in candidates if any(skill_lower in s.lower() for s in c.skills)]
    if language:
        language_lower = language.lower()
        candidates = [
            c for c in candidates
            if any(language_lower in (lang.get('language') or '').lower() for lang in c.languages)
        ]
    if min_experience:
        try:
            min_exp_value = float(min_experience)
            candidates = [c for c in candidates if (c.total_experience_years or 0) >= min_exp_value]
        except ValueError:
            pass

    return render(request, 'candidates/list.html', {
        'candidates': candidates,
        'hr_status_choices': HR_STATUS_CHOICES,
        'sort_options': SORT_OPTIONS,
        'filters': {
            'q': query, 'location': location, 'hr_status': hr_status,
            'skill': skill, 'language': language, 'min_experience': min_experience,
            'sort': sort,
        },
    })


@login_required
def cv_upload(request):
    """HR загружает один или несколько файлов CV; обработка уходит в фон (Django-Q2),
    HTTP-ответ не ждёт её завершения.
    """
    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, 'Please select at least one file.')
            return redirect('candidates:upload')

        for uploaded_file in files:
            candidate = Candidate.objects.create(source_file=uploaded_file, processing_status='pending')
            async_task('candidates.tasks.process_candidate_cv', candidate.id)

        messages.success(request, f'Uploaded {len(files)} file(s). Processing in background.')
        return redirect('candidates:list')

    return render(request, 'candidates/upload.html')


@login_required
def candidate_detail(request, pk):
    candidate = get_object_or_404(Candidate, pk=pk)

    if request.method == 'POST':
        candidate.hr_status = request.POST.get('hr_status', candidate.hr_status)
        candidate.hr_notes = request.POST.get('hr_notes', '')
        candidate.save(update_fields=['hr_status', 'hr_notes'])
        messages.success(request, 'Status updated.')
        return redirect('candidates:detail', pk=pk)

    source_file_ext = ''
    if candidate.source_file:
        source_file_ext = candidate.source_file.name.rsplit('.', 1)[-1].lower()

    return render(request, 'candidates/detail.html', {
        'candidate': candidate,
        'hr_status_choices': HR_STATUS_CHOICES,
        'source_file_is_pdf': source_file_ext == 'pdf',
        'source_file_is_image': source_file_ext in ('jpg', 'jpeg', 'png'),
    })


@login_required
def candidate_status_badge(request, pk):
    """Партиал для HTMX-поллинга статуса обработки сразу после загрузки CV."""
    candidate = get_object_or_404(Candidate, pk=pk)
    return render(request, 'candidates/_status_badge.html', {'candidate': candidate})


@login_required
def ai_search(request):
    """AI-поиск по базе на естественном языке: HR вводит запрос свободным текстом
    ("хочу full-stack разработчиков"), система ищет семантически близких
    кандидатов через pgvector и объясняет совпадение через LLM.
    """
    query_text = request.GET.get('q', '').strip()
    results = None
    if query_text:
        results = ai_search_module.search_candidates(query_text)

    return render(request, 'candidates/ai_search.html', {
        'query_text': query_text,
        'results': results,
    })

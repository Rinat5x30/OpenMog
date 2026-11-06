from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from candidates.models import Candidate
from vacancies.models import Vacancy


@login_required
def dashboard(request):
    candidates = Candidate.objects.all()
    stats = {
        'total_candidates': candidates.count(),
        'processing': candidates.filter(processing_status__in=['pending', 'processing']).count(),
        'done': candidates.filter(processing_status='done').count(),
        'error': candidates.filter(processing_status='error').count(),
        'open_vacancies': Vacancy.objects.filter(status='open').count(),
        'total_vacancies': Vacancy.objects.count(),
    }
    recent_candidates = candidates.order_by('-created_at')[:6]
    open_vacancies = Vacancy.objects.filter(status='open').order_by('-created_at')[:5]

    return render(request, 'dashboard.html', {
        'stats': stats,
        'recent_candidates': recent_candidates,
        'open_vacancies': open_vacancies,
    })

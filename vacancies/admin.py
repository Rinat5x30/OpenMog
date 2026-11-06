from django.contrib import admin

from .models import MatchResult, Vacancy


@admin.register(Vacancy)
class VacancyAdmin(admin.ModelAdmin):
    list_display = ('title', 'seniority', 'min_experience_years', 'status', 'created_at')
    list_filter = ('status', 'seniority', 'required_education_level')
    search_fields = ('title', 'raw_description', 'must_have_skills')
    readonly_fields = ('embedding', 'created_at')


@admin.register(MatchResult)
class MatchResultAdmin(admin.ModelAdmin):
    list_display = ('candidate', 'vacancy', 'final_score', 'passed_hard_filters', 'computed_at')
    list_filter = ('passed_hard_filters', 'vacancy')
    readonly_fields = ('computed_at',)

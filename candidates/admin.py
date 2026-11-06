from django.contrib import admin

from .models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'desired_position', 'location', 'total_experience_years',
        'processing_status', 'hr_status', 'created_at',
    )
    list_filter = ('processing_status', 'hr_status', 'language_detected', 'willing_to_relocate')
    search_fields = ('full_name', 'phone', 'email', 'desired_position', 'skills')
    readonly_fields = ('raw_text', 'corrected_text', 'embedding', 'created_at', 'updated_at')

from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import HnswIndex, VectorField

# Размерность эмбеддинга — nomic-embed-text (см. "Карта технологий" -> "Embedding-модель")
EMBEDDING_DIM = 768

LANGUAGE_DETECTED_CHOICES = [
    ('ru', 'Russian'),
    ('az', 'Azerbaijani'),
    ('en', 'English'),
]

PROCESSING_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('done', 'Done'),
    ('error', 'Error'),
]

HR_STATUS_CHOICES = [
    ('new', 'New'),
    ('contacted', 'Contacted'),
    ('interview', 'Interview'),
    ('rejected', 'Rejected'),
    ('hired', 'Hired'),
]


class Candidate(models.Model):
    # Контакты и основные данные
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    telegram = models.CharField(max_length=255, null=True, blank=True)
    linkedin = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    willing_to_relocate = models.BooleanField(null=True, blank=True)
    desired_position = models.CharField(max_length=255, null=True, blank=True)

    # Опыт и образование
    # total_experience_years считает LLM по датам из experience, если не указано явно в тексте
    total_experience_years = models.FloatField(null=True, blank=True)
    # JSONField, а не отдельная таблица — архитектурное решение для хакатона,
    # relational-запросы по опыту не нужны (см. "Карта данных" -> Candidate)
    experience = models.JSONField(default=list, blank=True)
    education = models.JSONField(default=list, blank=True)
    # ArrayField, а не JSONField — нужна индексируемая фильтрация skills__contains=[...]
    skills = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True)

    # Исходный и обработанный текст — для доверия/аудита HR
    raw_text = models.TextField(blank=True)
    corrected_text = models.TextField(blank=True)
    source_file = models.FileField(upload_to='cv/', null=True, blank=True)
    language_detected = models.CharField(
        max_length=2, choices=LANGUAGE_DETECTED_CHOICES, null=True, blank=True
    )

    # Semantic search (см. "Карта данных" -> MatchResult, "Матчинг под вакансию")
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True, blank=True)

    # processing_status — статус фонового AI-пайплайна;
    # hr_status — ручной статус рекрутёра. Намеренно раздельные поля,
    # чтобы не путать "AI закончил парсинг" с "рекрутёр поговорил с человеком".
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS_CHOICES, default='pending'
    )
    hr_status = models.CharField(
        max_length=20, choices=HR_STATUS_CHOICES, default='new'
    )
    hr_notes = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            HnswIndex(
                name='candidate_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ]

    def __str__(self):
        return self.full_name or f'Candidate #{self.pk}'

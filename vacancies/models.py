from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import HnswIndex, VectorField

from candidates.models import EMBEDDING_DIM, Candidate

EDUCATION_LEVEL_CHOICES = [
    ('none', 'No requirement'),
    ('secondary', 'Secondary'),
    ('bachelor', 'Bachelor'),
    ('master', 'Master'),
    ('phd', 'PhD'),
]

SENIORITY_CHOICES = [
    ('junior', 'Junior'),
    ('middle', 'Middle'),
    ('senior', 'Senior'),
    ('lead', 'Lead'),
]

VACANCY_STATUS_CHOICES = [
    ('open', 'Open'),
    ('closed', 'Closed'),
]


class Vacancy(models.Model):
    title = models.CharField(max_length=255)
    # исходный текст от HR, как ввели
    raw_description = models.TextField()

    # must_have_skills — жёсткий фильтр (гейт), а не вес в формуле (см. "Карта данных" -> MatchResult)
    must_have_skills = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    nice_to_have_skills = ArrayField(models.CharField(max_length=100), default=list, blank=True)
    min_experience_years = models.FloatField(null=True, blank=True)
    required_education_level = models.CharField(
        max_length=20, choices=EDUCATION_LEVEL_CHOICES, null=True, blank=True
    )
    # список {"language": str, "min_level": "native|fluent|intermediate|basic"}
    required_languages = models.JSONField(default=list, blank=True)
    seniority = models.CharField(max_length=20, choices=SENIORITY_CHOICES, null=True, blank=True)

    # вектор из raw_description/требований — для semantic search
    embedding = VectorField(dimensions=EMBEDDING_DIM, null=True, blank=True)

    status = models.CharField(max_length=20, choices=VACANCY_STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'vacancies'
        indexes = [
            HnswIndex(
                name='vacancy_embedding_hnsw',
                fields=['embedding'],
                m=16,
                ef_construction=64,
                opclasses=['vector_cosine_ops'],
            ),
        ]

    def __str__(self):
        return self.title


class MatchResult(models.Model):
    """Результат сравнения одного кандидата с одной вакансией.

    Формула final_score и гейты описаны в vacancies/matching.py
    (см. карточку "MatchResult" в Obsidian для обоснования весов).
    """

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='match_results')
    vacancy = models.ForeignKey(Vacancy, on_delete=models.CASCADE, related_name='match_results')

    semantic_similarity_score = models.FloatField(default=0.0)
    skill_overlap_score = models.FloatField(default=0.0)
    experience_score = models.FloatField(default=0.0)
    education_score = models.FloatField(default=0.0)

    passed_hard_filters = models.BooleanField(default=False)
    missing_must_have = ArrayField(models.CharField(max_length=100), default=list, blank=True)

    final_score = models.FloatField(default=0.0)
    explanation_text = models.TextField(null=True, blank=True)

    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('candidate', 'vacancy')
        ordering = ['-passed_hard_filters', '-final_score']

    def __str__(self):
        return f'{self.candidate} -> {self.vacancy} ({self.final_score:.2f})'

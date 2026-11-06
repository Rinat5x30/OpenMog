"""Определение языка CV (ru/az/en) — шаг 2 пайплайна (см. "Фоновая обработка CV").

Эвристика без доп. зависимостей: кириллица -> ru, уникальные
азербайджанские буквы латиницы (ə, ğ, ı, ö, ş, ü) -> az, иначе -> en.
"""

from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r'[а-яА-ЯёЁ]')
_AZERBAIJANI_RE = re.compile(r'[əğıöşüƏĞİÖŞÜ]')


def detect_language(text: str) -> str:
    if _CYRILLIC_RE.search(text):
        return 'ru'
    if _AZERBAIJANI_RE.search(text):
        return 'az'
    return 'en'

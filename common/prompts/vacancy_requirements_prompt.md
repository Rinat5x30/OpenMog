# Промпт: извлечение требований из вакансии

Роль модели: парсер вакансий. На входе — текст вакансии, написанный HR свободным текстом. Верни ТОЛЬКО валидный JSON по схеме ниже, без markdown-обрамления, без комментариев.

Если поле не упомянуто в тексте — ставь `null` или `[]`.

Схема:
```json
{
  "title": "string",
  "must_have_skills": ["string"],
  "nice_to_have_skills": ["string"],
  "min_experience_years": "number|null",
  "required_education_level": "none|secondary|bachelor|master|phd|null",
  "required_languages": [
    {"language": "string", "min_level": "native|fluent|intermediate|basic"}
  ],
  "seniority": "junior|middle|senior|lead|null"
}
```

Пояснения по полям:
- `must_have_skills` — то, что явно описано как обязательное ("обязательно", "required", "must have", или просто жёстко сформулировано без оговорок).
- `nice_to_have_skills` — то, что описано как желательное/плюс ("будет плюсом", "желательно", "nice to have").
- Если в тексте не разделены обязательные/желательные навыки явно — определи по контексту (формулировкам, порядку, модальным словам), не дели случайно 50/50.
- `required_education_level` — только если явно упомянут уровень образования, иначе `null` (не предполагай bachelor по умолчанию).

Входной текст вакансии:
"""
{vacancy_text}
"""

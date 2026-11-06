"""Извлечение текста из загруженного файла CV (см. "Парсинг файлов" в Obsidian).

PyMuPDF — PDF, python-docx — DOCX, pytesseract+Tesseract — сканы/фото
(языковые пакеты rus/aze/eng). Если PDF не содержит извлекаемого текстового
слоя (отсканированный документ), страницы прогоняются через OCR.
"""

from __future__ import annotations

import io
from pathlib import Path

import docx
import pymupdf as fitz
import pytesseract
from PIL import Image

TESSERACT_LANGS = 'rus+aze+eng'
OCR_DPI = 300


class UnsupportedFileType(Exception):
    pass


def _ocr_image(image: Image.Image) -> str:
    return pytesseract.image_to_string(image, lang=TESSERACT_LANGS).strip()


def _parse_pdf(file_path: str | Path) -> str:
    doc = fitz.open(file_path)
    try:
        text = '\n'.join(page.get_text() for page in doc).strip()
        if text:
            return text
        # нет текстового слоя — вероятно, отсканированный PDF, распознаём по страницам
        parts = []
        for page in doc:
            pixmap = page.get_pixmap(dpi=OCR_DPI)
            image = Image.open(io.BytesIO(pixmap.tobytes('png')))
            parts.append(_ocr_image(image))
        return '\n'.join(parts).strip()
    finally:
        doc.close()


def _parse_docx(file_path: str | Path) -> str:
    document = docx.Document(file_path)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Многие CV-шаблоны верстают весь текст внутри таблицы (контактная колонка,
    # основной блок) — document.paragraphs их не видит, нужен отдельный обход.
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)
    return '\n'.join(parts).strip()


def _parse_image(file_path: str | Path) -> str:
    image = Image.open(file_path)
    return _ocr_image(image)


_PARSERS = {
    '.pdf': _parse_pdf,
    '.docx': _parse_docx,
    '.png': _parse_image,
    '.jpg': _parse_image,
    '.jpeg': _parse_image,
}


def parse_cv_file(file_path: str | Path) -> str:
    """Возвращает сырой текст CV. Бросает UnsupportedFileType для неизвестных расширений."""
    ext = Path(file_path).suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise UnsupportedFileType(f'Неподдерживаемый тип файла: {ext}')
    return parser(file_path)

"""Import pipeline for pamphlets_extracted_by_page.json.

Usage (Flask CLI):
    flask import-pamphlets path/to/pamphlets_extracted_by_page.json

Programmatic usage:
    from app.services.pamphlet_importer import import_pamphlet_json
    result = import_pamphlet_json('path/to/pamphlets_extracted_by_page.json')
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalize extracted text for storage."""
    if not text:
        return ''
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.strip()
    # Collapse 3+ consecutive newlines to a paragraph break
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Collapse multiple spaces / tabs on a single line to one space
    text = re.sub(r'[ \t]+', ' ', text)
    # Strip trailing whitespace from every line
    text = '\n'.join(line.rstrip() for line in text.split('\n'))
    return text


def _get_page_label(page: dict) -> str:
    """Return the page label to store (printed when detected, else relative)."""
    if page.get('printed_page_number_detected'):
        return str(page['printed_page_number'])
    return str(page['relative_page_number'])


def _get_series(filename: str) -> str:
    """Extract the series code (text before the first underscore)."""
    return filename.split('_')[0]


def _derive_title(doc: dict) -> str:
    """Return the best available title for the document."""
    title = doc.get('metadata_title')
    if title:
        return title.strip()
    # Fall back to filename: strip series prefix and .pdf extension
    filename = doc['filename']
    name = filename.rsplit('.', 1)[0]
    parts = name.split('_', 1)
    return parts[1].replace('_', ' ') if len(parts) > 1 else name


# ---------------------------------------------------------------------------
# Content row builder
# ---------------------------------------------------------------------------

def _build_content_rows(pamphlet_id: int, doc: dict) -> list:
    """Return a list of unsaved PamphletContent objects for one document."""
    from app.models import PamphletContent

    rows = []

    for page in doc.get('pages', []):
        page_label = _get_page_label(page)
        para_counter = 0

        # ------------------------------------------------------------------
        # Regular sections
        # ------------------------------------------------------------------
        for section in page.get('sections', []):
            header_text = section.get('header')
            body_text = section.get('text', '')

            if header_text:
                normalized = _normalize_text(header_text)
                if normalized:
                    rows.append(PamphletContent(
                        pamphlet_id=pamphlet_id,
                        content_mode='header',
                        page=page_label,
                        paragraph=0,
                        line=None,
                        content=normalized,
                    ))

            if body_text:
                normalized = _normalize_text(body_text)
                for para in [p.strip() for p in normalized.split('\n\n') if p.strip()]:
                    para_counter += 1
                    rows.append(PamphletContent(
                        pamphlet_id=pamphlet_id,
                        content_mode='page',
                        page=page_label,
                        paragraph=para_counter,
                        line=None,
                        content=para,
                    ))

        # ------------------------------------------------------------------
        # Boxed / sidebar sections
        # ------------------------------------------------------------------
        for boxed in page.get('boxed_sections', []):
            for section in boxed.get('sections', []):
                header_text = section.get('header')
                body_text = section.get('text', '')

                if header_text:
                    normalized = _normalize_text(header_text)
                    if normalized:
                        rows.append(PamphletContent(
                            pamphlet_id=pamphlet_id,
                            content_mode='header',
                            page=page_label,
                            paragraph=0,
                            line=None,
                            content=normalized,
                        ))

                if body_text:
                    normalized = _normalize_text(body_text)
                    for para in [p.strip() for p in normalized.split('\n\n') if p.strip()]:
                        para_counter += 1
                        rows.append(PamphletContent(
                            pamphlet_id=pamphlet_id,
                            content_mode='sidebar',
                            page=page_label,
                            paragraph=para_counter,
                            line=None,
                            content=para,
                        ))

        # ------------------------------------------------------------------
        # Extraction warnings (blank / image-only pages)
        # ------------------------------------------------------------------
        extraction_note = page.get('extraction_note')
        if extraction_note:
            rows.append(PamphletContent(
                pamphlet_id=pamphlet_id,
                content_mode='warning',
                page=page_label,
                paragraph=None,
                line=None,
                content=_normalize_text(extraction_note),
            ))

    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def import_pamphlet_json(filepath) -> dict:
    """Import all pamphlets from a JSON extraction file into the database.

    Each document in the JSON is mapped to one Pamphlet record plus many
    PamphletContent records.  Import is idempotent: an existing pamphlet
    (matched by series) has its content replaced and its metadata updated.
    A failure in one pamphlet does not abort the remaining ones.

    Returns a summary dict with keys: pamphlets, pages, rows, errors.
    """
    from app import db
    from app.models import Pamphlet, PamphletContent

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    documents = data.get('documents', [])
    total_pamphlets = 0
    total_pages = 0
    total_rows = 0
    total_errors = 0

    for doc in documents:
        filename = doc['filename']
        series = _get_series(filename)
        title = _derive_title(doc)
        pdf_path = doc.get('path_in_zip') or filename
        page_count = doc.get('page_count', len(doc.get('pages', [])))

        try:
            existing = Pamphlet.query.filter_by(series=series).first()

            if existing:
                # Delete existing content rows, then update metadata
                PamphletContent.query.filter_by(pamphlet_id=existing.id).delete()
                existing.title = title
                existing.pdf_path = pdf_path
                pamphlet = existing
                logger.info("Updating pamphlet: %s (%s)", title, series)
            else:
                pamphlet = Pamphlet(
                    title=title,
                    series=series,
                    publisher='AA World Services',
                    pdf_path=pdf_path,
                    notes=None,
                )
                db.session.add(pamphlet)
                logger.info("Creating pamphlet: %s (%s)", title, series)

            # Flush so pamphlet.id is available before building content rows
            db.session.flush()

            rows = _build_content_rows(pamphlet.id, doc)
            db.session.bulk_save_objects(rows)
            db.session.commit()

            total_pamphlets += 1
            total_pages += page_count
            total_rows += len(rows)

            logger.info(
                "  OK  %-60s series=%-10s pages=%3d  rows=%4d",
                title[:60], series, page_count, len(rows),
            )

        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            total_errors += 1
            logger.error("Error importing '%s' (%s): %s", title, series, exc)
            continue

    logger.info(
        "\nImport summary:\n"
        "  Pamphlets imported : %d\n"
        "  Pages imported     : %d\n"
        "  Content rows       : %d\n"
        "  Errors             : %d",
        total_pamphlets, total_pages, total_rows, total_errors,
    )

    return {
        'pamphlets': total_pamphlets,
        'pages': total_pages,
        'rows': total_rows,
        'errors': total_errors,
    }

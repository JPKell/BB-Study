from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
import re
from textwrap import shorten

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from ..models import (Book, BookContent, BookContentFormat, BookLocation, BookPageFormat,
                      BookReference, Commentary, DictionaryLookup, Source)


@dataclass
class TextStyle:
    font: str = 'Times-Roman'
    bold_font: str = 'Times-Bold'
    size: float = 10
    leading: float = 14
    char_spacing: float = 0
    color: colors.Color = colors.black
    role_styles: dict = field(default_factory=dict)


@dataclass
class ExportLayout:
    page_size: tuple = letter
    outside_margin: float = 0.45 * inch
    inside_margin: float = 0.8 * inch
    annotation_margin: float = 0.45 * inch
    top_margin: float = 0.45 * inch
    bottom_margin: float = 0.45 * inch
    page_number_gap: float = 0.35 * inch
    column_gutter: float = 0.22 * inch
    text_ratio: float = 2 / 3
    commentary_columns: int = 3
    commentary_column_gutter: float = 0.32 * inch
    one_column_top: bool = False
    book_alignment: str = 'justify'
    definition_alignment: str = 'left'
    commentary_alignment: str = 'left'
    annotation_alignment: str = 'left'
    content_role_styles: dict = field(default_factory=dict)
    section_gap: float = 0.18 * inch
    header_gap: float = 0.46 * inch
    rule_margin_above: float = 0.04 * inch
    rule_margin_below: float = 0.21 * inch
    top_min_height: float = 2.2 * inch
    text_layout: str = 'reflow_justified'
    chapter_font_size: float = 8.5
    page_number_font_size: float = 8
    book_font_size: float = 10.2
    definition_font_size: float = 8.3
    commentary_font_size: float = 7.0
    annotation_font_size: float = 9.0
    chapter_line_spacing: float = 1.0
    page_number_line_spacing: float = 1.0
    book_line_spacing: float = 1.35
    definition_line_spacing: float = 1.3
    commentary_line_spacing: float = 1.28
    annotation_line_spacing: float = 1.33
    chapter_kerning: float = 0
    page_number_kerning: float = 0
    book_kerning: float = 0
    definition_kerning: float = 0
    commentary_kerning: float = 0
    annotation_kerning: float = 0
    chapter_font: str = 'Helvetica'
    page_number_font: str = 'Helvetica'
    chapter_bold: bool = False
    chapter_italic: bool = False
    page_number_bold: bool = False
    page_number_italic: bool = False
    book_font: str = 'Times-Roman'
    definition_font: str = 'Helvetica'
    commentary_font: str = 'Helvetica'
    annotation_font: str = 'Helvetica'
    chapter_gray: float = 30
    page_number_gray: float = 40
    book_gray: float = 0
    definition_gray: float = 0
    commentary_gray: float = 0
    annotation_gray: float = 0


@dataclass
class PageExportData:
    book: Book
    page: str
    relative_page_number: int | None
    chapter: str
    content_rows: list
    format_map: dict
    paragraphs: list
    definitions: list
    commentary_rows: list
    commentary: list
    commentary_markers: dict
    references: list
    sources: list
    page_format: BookPageFormat | None = None


def export_page_pdf(book_id, page, layout=None):
    """Return PDF bytes for one book page and its annotations."""
    layout = layout or ExportLayout()
    data = collect_page_export_data(book_id, page)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=layout.page_size)
    set_pdf_title(pdf, [data])
    render_page_export(pdf, data, layout)
    pdf.save()
    buffer.seek(0)
    return buffer


def export_pages_pdf(book_id, pages, layout=None):
    """Return PDF bytes for multiple book pages in one PDF."""
    layout = layout or ExportLayout()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=layout.page_size)
    title_data = []
    for index, page in enumerate(pages):
        if index:
            pdf.showPage()
        if page is None:
            if index == 0:
                title_data = [collect_page_export_data(book_id, title_page) for title_page in pages if title_page is not None]
                set_pdf_title(pdf, title_data)
            render_blank_export_page(pdf, layout)
            continue
        data = collect_page_export_data(book_id, page)
        if index == 0:
            title_data = [data]
            for title_page in pages[1:]:
                if title_page is not None:
                    title_data.append(collect_page_export_data(book_id, title_page))
            set_pdf_title(pdf, title_data)
        render_page_export(pdf, data, layout)
    pdf.save()
    buffer.seek(0)
    return buffer


def set_pdf_title(pdf, pages):
    if not pages:
        return
    book_title = pages[0].book.title if pages[0].book else 'Export'
    page_label = '-'.join(str(page.page) for page in pages if page)
    chapter_titles = []
    for page in pages:
        title = page.chapter or page.book.title
        if title and title not in chapter_titles:
            chapter_titles.append(title)
    title_bits = [book_title]
    if chapter_titles:
        title_bits.append(' / '.join(chapter_titles))
    title_bits.append(f'page {page_label}')
    pdf.setTitle(' - '.join(title_bits))


def collect_page_export_data(book_id, page):
    book = Book.query.get_or_404(book_id)
    rows = (BookContent.query
            .filter_by(book_id=book_id, page=page)
            .order_by(BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id)
            .all())
    chapter = next((r.chapter_name or r.chapter for r in rows if r.chapter_name or r.chapter), '')
    relative_page_number = next((r.relative_page_number for r in rows if r.relative_page_number), None)
    commentary = (Commentary.query
                  .filter_by(book_id=book_id, page=page)
                  .order_by(Commentary.created_at)
                  .all())
    commentary = sort_commentary_by_text_order(rows, commentary)
    references = (BookReference.query
                  .filter(BookReference.source_book_id == book_id,
                          BookReference.source_page == page)
                  .order_by(BookReference.created_at)
                  .all())
    sources = (Source.query
               .filter_by(book_id=book_id, page=page)
               .order_by(Source.created_at)
               .all())

    loc_ids = [loc.id for loc in BookLocation.query.filter_by(book_id=book_id, page=page).all()]
    definitions = []
    if loc_ids:
        definitions = (DictionaryLookup.query
                       .filter(DictionaryLookup.book_location_id.in_(loc_ids))
                       .all())

    format_map = collect_content_formats(book_id, page)
    page_format = BookPageFormat.query.filter_by(book_id=book_id, page=str(page)).first()
    data = PageExportData(book, str(page), relative_page_number, chapter, rows, format_map, [], definitions,
                          commentary, [], {}, references, sources, page_format)
    refresh_commentary_export(data)
    return data


def refresh_commentary_export(data):
    _, fallback_location = page_location_order(data.content_rows)
    commentary_items, commentary_markers = build_annotation_markers(
        annotation_note_rows(data),
        fallback_location=fallback_location,
    )
    data.commentary = commentary_items
    data.commentary_markers = commentary_markers
    data.paragraphs = build_marked_page_paragraphs(data.content_rows, commentary_markers, data.format_map)


def annotation_note_rows(data):
    rows = (
        [('commentary', row) for row in data.commentary_rows]
        + [('reference', row) for row in data.references]
        + [('source', row) for row in data.sources]
    )
    location_order, fallback_location = page_location_order(data.content_rows)
    return sorted(
        rows,
        key=lambda item: annotation_text_sort_key(item, location_order, fallback_location),
    )


def page_location_order(rows):
    order = {}
    fallback_location = (None, None)
    for row in rows:
        key = location_key(row.paragraph, row.verse)
        if fallback_location == (None, None) and row.paragraph is not None:
            fallback_location = key
        if row.paragraph is not None and row.verse is not None and key not in order:
            order[key] = len(order)
    return order, fallback_location


def annotation_text_sort_key(item, location_order, fallback_location):
    kind, row = item
    paragraph, verse = annotation_location(kind, row, fallback_location)
    location_index = annotation_location_index(paragraph, verse, location_order)
    return (location_index, paragraph or 0, verse or 0, *rank_sort_key(row))


def annotation_location_index(paragraph, verse, location_order):
    key = location_key(paragraph, verse)
    if key in location_order:
        return location_order[key]
    paragraph_indexes = [
        index
        for (row_paragraph, _), index in location_order.items()
        if row_paragraph == paragraph
    ]
    if paragraph_indexes:
        return min(paragraph_indexes)
    return -1


def sort_ranked_items(rows):
    return sorted(rows, key=rank_sort_key)


def sort_definitions_alpha(lookups):
    return sorted(lookups, key=definition_alpha_key)


def definition_alpha_key(lookup):
    entry = getattr(lookup, 'entry', None)
    word = (getattr(entry, 'word_phrase', '') or '').casefold()
    return (word, getattr(lookup, 'id', 0) or 0)


def rank_sort_key(row):
    rank = getattr(row, 'rank', None)
    rank_value = rank if rank is not None and rank > 0 else 1000000
    created_at = getattr(row, 'created_at', None) or datetime.min
    return (rank_value, created_at, getattr(row, 'id', 0) or 0)


def collect_content_formats(book_id, page):
    formats = BookContentFormat.query.filter_by(book_id=book_id, page=page).all()
    return {
        location_key(fmt.paragraph, fmt.verse): fmt
        for fmt in formats
        if fmt.paragraph is not None and fmt.verse is not None
    }


def sort_commentary_by_text_order(rows, commentary):
    location_order = {}
    for row in rows:
        key = location_key(row.paragraph, row.verse)
        if key not in location_order:
            location_order[key] = len(location_order)

    def sort_key(row):
        page_order = location_order.get(location_key(row.paragraph, row.verse))
        created_at = row.created_at or datetime.min
        if page_order is not None:
            return (0, page_order, created_at, row.id)
        paragraph = row.paragraph if row.paragraph is not None else 999999
        verse = row.verse if row.verse is not None else 999999
        return (1, paragraph, verse, created_at, row.id)

    return sorted(commentary, key=sort_key)


def build_commentary_markers(commentary):
    return build_annotation_markers([('commentary', row) for row in commentary])


def build_annotation_markers(annotation_rows, fallback_location=None):
    markers = {}
    items = []
    fallback_location = fallback_location or first_annotation_location(annotation_rows)
    for index, (kind, row) in enumerate(annotation_rows, start=1):
        paragraph, verse = annotation_location(kind, row, fallback_location)
        marker = {
            'number': index,
            'line_text': normalize_match_text(annotation_note_text(kind, row)),
        }
        markers.setdefault(location_key(paragraph, verse), []).append(marker)
        markers.setdefault(paragraph_key(paragraph), []).append((verse, marker))
        items.append((index, kind, row))
    return items, markers


def first_annotation_location(annotation_rows):
    for kind, row in annotation_rows:
        paragraph, verse = annotation_location(kind, row)
        if paragraph is not None:
            return paragraph, verse
    return (None, None)


def annotation_location(kind, row, fallback_location=None):
    if kind == 'reference':
        paragraph, verse = row.source_paragraph, row.source_verse
    else:
        paragraph, verse = row.paragraph, row.verse
    if paragraph is None and fallback_location:
        return fallback_location
    if verse is None and fallback_location and paragraph == fallback_location[0]:
        return fallback_location
    return paragraph, verse


def annotation_note_text(kind, row):
    if kind == 'commentary':
        return row.commentary_text or ''
    if kind == 'reference':
        return format_reference(row)
    return format_source(row)


def build_marked_page_paragraphs(rows, commentary_markers, format_map=None):
    format_map = format_map or {}
    paragraphs = []
    current_paragraph = object()
    current_rows = []
    for row in rows:
        key = row.paragraph if row.paragraph is not None else row.id
        if current_rows and key != current_paragraph:
            paragraphs.append(build_paragraph_segments(current_rows, commentary_markers, format_map))
            current_rows = []
        current_paragraph = key
        current_rows.append(row)
    if current_rows:
        paragraphs.append(build_paragraph_segments(current_rows, commentary_markers, format_map))
    return [paragraph for paragraph in paragraphs if paragraph]


def build_paragraph_segments(rows, commentary_markers, format_map):
    segments = []
    current_key = object()
    current_rows = []
    verse_values = {row.verse for row in rows}
    used_marker_keys = set()
    for row in rows:
        key = (row.paragraph, row.line if row.line is not None else row.id)
        if current_rows and key != current_key:
            segments.append(build_line_segment(current_rows, commentary_markers, used_marker_keys, format_map))
            current_rows = []
        current_key = key
        current_rows.append(row)
    if current_rows:
        segments.append(build_line_segment(current_rows, commentary_markers, used_marker_keys, format_map))
    apply_unmatched_paragraph_markers(segments, rows[0].paragraph if rows else None, verse_values, commentary_markers)
    return [segment for segment in segments if segment['text']]


def build_line_segment(rows, commentary_markers, used_marker_keys, format_map):
    fragments = []
    for row in rows:
        key = location_key(row.paragraph, row.verse)
        markers = []
        if key not in used_marker_keys:
            markers = list(commentary_markers.get(key, []))
            if markers:
                used_marker_keys.add(key)
        fragments.append({
            'text': row.content or '',
            'markers': markers,
            'verse': row.verse,
            'is_bold': bool(format_map.get(key) and format_map[key].is_bold),
            'is_italic': bool(format_map.get(key) and format_map[key].is_italic),
            'content_role': format_map[key].content_role if format_map.get(key) else 'body',
            'alignment_override': format_map[key].alignment_override if format_map.get(key) else '',
        })
    return {
        'fragments': fragments,
        'text': combine_content_fragments(rows),
    }


def location_key(paragraph, line):
    return (paragraph, line)


def paragraph_key(paragraph):
    return ('paragraph', paragraph)


def apply_unmatched_paragraph_markers(segments, paragraph, verse_values, commentary_markers):
    if not segments:
        return
    flattened = [fragment for segment in segments for fragment in segment.get('fragments', [])]
    for verse, marker in commentary_markers.get(paragraph_key(paragraph), []):
        if verse in verse_values:
            continue
        target_index = 0
        if isinstance(verse, int) and 1 <= verse <= len(flattened):
            target_index = verse - 1
        if flattened and not flattened[target_index].get('markers'):
            flattened[target_index]['markers'] = [marker]


def combine_content_fragments(rows):
    text = ''
    for row in rows:
        part = row.content or ''
        if not part:
            continue
        if not text:
            text = part
        elif text.endswith('-'):
            text = text[:-1] + part
        else:
            text = f'{text} {part}'
    return ' '.join(text.split())


def normalize_match_text(text):
    return ' '.join((text or '').lower().split())


def render_page_export(pdf, data, layout):
    if getattr(data.page_format, 'centered_export', False):
        render_centered_text_page(pdf, data, layout)
        return
    width, height = layout.page_size
    y = height - layout.top_margin
    y = draw_export_header(pdf, data, layout, y)
    prepare_page_export_data(data, layout, y)
    y = draw_book_and_definitions(pdf, data, layout, y)
    y -= layout.section_gap
    y = draw_annotation_sections(pdf, data, layout, y)
    draw_footer(pdf, data, layout)


def render_blank_export_page(pdf, layout):
    return


def render_centered_text_page(pdf, data, layout):
    width, height = layout.page_size
    horizontal_margin = max(layout.inside_margin, layout.outside_margin)
    text_width = width - (horizontal_margin * 2)
    text_style = TextStyle(font=layout.book_font, bold_font=bold_font_for(layout.book_font),
                           size=layout.book_font_size, leading=layout.book_font_size * layout.book_line_spacing,
                           char_spacing=layout.book_kerning,
                           color=grayscale_color(layout.book_gray),
                           role_styles=layout.content_role_styles)
    text_height = measure_paragraph_block(data.paragraphs, text_width, text_style,
                                          text_layout=layout.text_layout)
    y = (height + text_height) / 2
    draw_paragraph_block(pdf, data.paragraphs, horizontal_margin, y, text_width, text_style,
                         text_layout=layout.text_layout, alignment='center',
                         force_alignment='center')


def prepare_page_export_data(data, layout, y):
    if not layout.one_column_top:
        data.definitions = prune_side_definitions(data, layout, y)
    after_book_y = y - measure_book_block_height(data, layout)
    prune_bottom_annotations(data, layout, after_book_y - layout.section_gap)
    refresh_commentary_export(data)


def measure_book_block_height(data, layout):
    width, _ = layout.page_size
    text_on_left = is_inside_text_left(data)
    left_margin, right_margin = page_margins(layout, text_on_left)
    content_width = width - left_margin - right_margin
    text_width = content_width if layout.one_column_top else (content_width - layout.column_gutter) * layout.text_ratio
    side_width = 0 if layout.one_column_top else content_width - layout.column_gutter - text_width
    text_style = TextStyle(font=layout.book_font, bold_font=bold_font_for(layout.book_font),
                           size=layout.book_font_size, leading=layout.book_font_size * layout.book_line_spacing,
                           char_spacing=layout.book_kerning,
                           color=grayscale_color(layout.book_gray),
                           role_styles=layout.content_role_styles)
    side_style = TextStyle(font=layout.definition_font, bold_font=bold_font_for(layout.definition_font),
                           size=layout.definition_font_size,
                           leading=layout.definition_font_size * layout.definition_line_spacing,
                           char_spacing=layout.definition_kerning,
                           color=grayscale_color(layout.definition_gray))
    title_style = TextStyle(font=bold_font_for(layout.definition_font), bold_font=bold_font_for(layout.definition_font),
                            size=layout.definition_font_size,
                            leading=layout.definition_font_size * layout.definition_line_spacing,
                            char_spacing=layout.definition_kerning,
                            color=grayscale_color(layout.definition_gray))
    text_height = measure_paragraph_block(data.paragraphs, text_width, text_style,
                                          text_layout=layout.text_layout)
    side_height = 0 if layout.one_column_top else measure_labeled_items(
        format_definitions(sort_definitions_alpha(data.definitions)), side_width, side_style, title_style,
    )
    return max(layout.top_min_height, text_height, side_height)


def prune_side_definitions(data, layout, y):
    width, _ = layout.page_size
    left_margin, right_margin = page_margins(layout, is_inside_text_left(data))
    content_width = width - left_margin - right_margin
    text_width = (content_width - layout.column_gutter) * layout.text_ratio
    side_width = content_width - layout.column_gutter - text_width
    style = TextStyle(font=layout.definition_font, bold_font=bold_font_for(layout.definition_font),
                      size=layout.definition_font_size,
                      leading=layout.definition_font_size * layout.definition_line_spacing,
                      char_spacing=layout.definition_kerning,
                      color=grayscale_color(layout.definition_gray))
    title_style = TextStyle(font=bold_font_for(layout.definition_font), bold_font=bold_font_for(layout.definition_font),
                            size=layout.definition_font_size,
                            leading=layout.definition_font_size * layout.definition_line_spacing,
                            char_spacing=layout.definition_kerning,
                            color=grayscale_color(layout.definition_gray))
    available = max(0, y - layout.bottom_margin)
    kept = []
    for definition in sort_ranked_items(data.definitions):
        trial = kept + [definition]
        if measure_labeled_items(format_definitions(sort_definitions_alpha(trial)), side_width, style, title_style) <= available:
            kept = trial
    return kept


def prune_bottom_annotations(data, layout, y):
    pool = annotation_prune_pool(data, layout)
    if not pool:
        return
    kept = set()
    for candidate in sorted(pool, key=annotation_candidate_drop_key):
        trial = set(kept)
        trial.add(candidate)
        if annotation_pool_fits(data, layout, y, trial):
            kept = trial
    data.commentary_rows = [row for row in data.commentary_rows if annotation_candidate('commentary', row) in kept]
    data.references = [row for row in data.references if annotation_candidate('reference', row) in kept]
    data.sources = [row for row in data.sources if annotation_candidate('source', row) in kept]
    if layout.one_column_top:
        data.definitions = [row for row in data.definitions if annotation_candidate('definition', row) in kept]


def annotation_prune_pool(data, layout):
    candidates = []
    if layout.one_column_top:
        candidates.extend(annotation_candidate('definition', row) for row in data.definitions)
    candidates.extend(annotation_candidate('commentary', row) for row in data.commentary_rows)
    candidates.extend(annotation_candidate('reference', row) for row in data.references)
    candidates.extend(annotation_candidate('source', row) for row in data.sources)
    return candidates


def annotation_candidate(kind, row):
    return (kind, getattr(row, 'id', id(row)), row)


def annotation_candidate_drop_key(candidate):
    _, _, row = candidate
    rank = getattr(row, 'rank', None)
    rank_value = rank if rank is not None and rank > 0 else 1000000
    created_at = getattr(row, 'created_at', None) or datetime.min
    return (rank_value, created_at, getattr(row, 'id', 0) or 0)


def annotation_pool_fits(data, layout, y, kept):
    sample = annotation_data_for_kept(data, layout, kept)
    return measure_annotation_sections_height(sample, layout, y) <= max(0, y - layout.bottom_margin)


def annotation_data_for_kept(data, layout, kept):
    definitions = data.definitions
    if layout.one_column_top:
        definitions = [row for row in data.definitions if annotation_candidate('definition', row) in kept]
    commentary_rows = [row for row in data.commentary_rows if annotation_candidate('commentary', row) in kept]
    references = [row for row in data.references if annotation_candidate('reference', row) in kept]
    sources = [row for row in data.sources if annotation_candidate('source', row) in kept]
    return definitions, commentary_rows, references, sources


def measure_annotation_sections_height(sample, layout, y):
    definitions, commentary_rows, references, sources = sample
    height = 0
    commentary_items = []
    if layout.one_column_top:
        commentary_items.extend(format_definition_commentary_items(sort_definitions_alpha(definitions)))
    note_rows = (
        [('commentary', row) for row in commentary_rows]
        + [('reference', row) for row in references]
        + [('source', row) for row in sources]
    )
    commentary_items.extend(format_commentary(build_annotation_markers(sorted(note_rows, key=lambda item: rank_sort_key(item[1])))[0]))
    if commentary_items:
        column_height, fits = measure_commentary_columns_height(commentary_items, layout, y)
        if not fits:
            return y - layout.bottom_margin + 1
        height += column_height
    return height


def measure_commentary_columns_height(items, layout, y):
    width = layout.page_size[0] - (2 * layout.annotation_margin)
    column_count = max(1, min(4, int(layout.commentary_columns or 3)))
    column_width = (width - (layout.commentary_column_gutter * (column_count - 1))) / column_count
    style = TextStyle(font=layout.commentary_font, bold_font=bold_font_for(layout.commentary_font),
                      size=layout.commentary_font_size,
                      leading=layout.commentary_font_size * layout.commentary_line_spacing,
                      char_spacing=layout.commentary_kerning,
                      color=grayscale_color(layout.commentary_gray))
    label_style = TextStyle(font=bold_font_for(layout.commentary_font),
                            bold_font=bold_font_for(layout.commentary_font),
                            size=max(5.5, layout.commentary_font_size - 0.8), leading=8,
                            char_spacing=layout.commentary_kerning,
                            color=grayscale_color(layout.commentary_gray))
    column_items, wide_items = split_wide_annotation_items(items, column_width, style)
    top_offset = measure_section_heading_height(layout)
    wide_height = measure_wide_annotation_items_height(wide_items, width, style, label_style)
    bottom_limit = annotation_column_bottom_limit(layout, wide_height)
    column_available = max(0, y - bottom_limit - top_offset)
    if column_available < 0:
        return y - layout.bottom_margin + 1, False
    column_height, fits = measure_column_annotation_items_height(
        column_items, column_width, column_count, column_available, style, label_style,
    )
    if not fits:
        return y - layout.bottom_margin + 1, False
    used_to_columns = top_offset + column_height
    used_to_footer = max(0, y - footer_url_block_bottom_y(layout)) if wide_items else 0
    return max(used_to_columns, used_to_footer), True


def measure_column_annotation_items_height(items, column_width, column_count, available, style, label_style):
    columns, fits = allocate_annotation_columns(
        items, column_width, column_count, available, style, label_style,
    )
    if not fits:
        return available + 1, False
    return max((column['height'] for column in columns), default=0), True


def allocate_annotation_columns(items, column_width, column_count, available, style, label_style):
    column_count = max(1, int(column_count or 1))
    item_entries = []
    for item in items:
        height = measure_commentary_item_height(item, column_width, style, label_style)
        height += annotation_column_item_gap()
        item_entries.append({'item': item, 'height': height})

    columns = [{'items': [], 'height': 0} for _ in range(column_count)]
    if not item_entries:
        return columns, True

    active_columns = min(column_count, len(item_entries))
    if all(entry['height'] <= available for entry in item_entries):
        partitioned_columns = partition_annotation_items(item_entries, active_columns)
        columns[:active_columns] = partitioned_columns
        if not any(column['height'] > available for column in columns):
            return columns, True

    flow_columns, fits = allocate_flowing_annotation_columns(
        items, column_width, column_count, available, style, label_style,
    )
    if not fits:
        return [], False
    columns[:len(flow_columns)] = flow_columns
    return columns, True


def allocate_flowing_annotation_columns(items, column_width, column_count, available, style, label_style):
    if available < style.leading:
        return [], False

    column_heights = flowing_annotation_column_heights(
        items, column_width, column_count, available, style, label_style, prefer_clean_item_starts=True,
    )
    if column_heights is None:
        column_heights = flowing_annotation_column_heights(
            items, column_width, column_count, available, style, label_style, prefer_clean_item_starts=False,
        )
    if column_heights is None:
        return [], False
    columns = [{'items': [], 'height': height, 'flow': True} for height in column_heights]
    if columns:
        columns[0]['items'] = items
    return columns, True


def flowing_annotation_column_heights(items, column_width, column_count, available, style, label_style,
                                      prefer_clean_item_starts=False):
    column_index = 0
    column_heights = [0 for _ in range(column_count)]
    remaining = available
    previous_item_spilled = False
    for item in items:
        line_heights = annotation_item_line_heights(item, column_width, style, label_style)
        item_height = sum(line_heights) + annotation_column_item_gap()
        if (
            prefer_clean_item_starts
            and previous_item_spilled
            and column_heights[column_index] > 0
            and item_height <= available
            and any(height == 0 for height in column_heights[column_index + 1:])
        ):
            column_index += 1
            if column_index >= column_count:
                return None
            remaining = available
        start_column = column_index
        for line_height in line_heights:
            if line_height > available:
                return None
            if remaining < line_height:
                column_index += 1
                if column_index >= column_count:
                    return None
                remaining = available
            column_heights[column_index] += line_height
            remaining -= line_height
        gap = annotation_column_item_gap()
        if remaining >= gap:
            column_heights[column_index] += gap
            remaining -= gap
        else:
            column_heights[column_index] = available
            remaining = 0
        previous_item_spilled = column_index > start_column
    return column_heights


def annotation_item_line_heights(item, width, style, label_style):
    line_count = max(1, round(measure_commentary_item_height(item, width, style, label_style) / style.leading))
    return [style.leading for _ in range(line_count)]


def partition_annotation_items(item_entries, column_count):
    prefix_heights = [0]
    for entry in item_entries:
        prefix_heights.append(prefix_heights[-1] + entry['height'])

    best_breaks = None
    best_score = None
    for breaks in annotation_column_breaks(len(item_entries), column_count):
        heights = partition_heights(prefix_heights, breaks)
        score = annotation_partition_score(heights, breaks)
        if best_score is None or score < best_score:
            best_breaks = breaks
            best_score = score

    columns = []
    start = 0
    for end in best_breaks:
        height = prefix_heights[end] - prefix_heights[start]
        columns.append({
            'items': [entry['item'] for entry in item_entries[start:end]],
            'height': height,
        })
        start = end
    return columns


def annotation_column_breaks(item_count, column_count, start=0):
    if column_count == 1:
        yield [item_count]
        return
    end_limit = item_count - column_count + 1
    for end in range(start + 1, end_limit + 1):
        for breaks in annotation_column_breaks(item_count, column_count - 1, end):
            yield [end, *breaks]


def partition_heights(prefix_heights, breaks):
    heights = []
    start = 0
    for end in breaks:
        heights.append(prefix_heights[end] - prefix_heights[start])
        start = end
    return heights


def annotation_partition_score(heights, breaks):
    right_heavy = sum(max(0, heights[index] - heights[index - 1]) for index in range(1, len(heights)))
    height_range = max(heights) - min(heights)
    max_height = max(heights)
    item_counts = [breaks[0], *(breaks[index] - breaks[index - 1] for index in range(1, len(breaks)))]
    return (
        height_range + (right_heavy * 2),
        right_heavy,
        height_range,
        max_height,
        tuple(-count for count in item_counts[:-1]),
    )


def annotation_column_item_gap():
    return 0.12 * inch


def split_wide_annotation_items(items, column_width, style):
    column_items = []
    wide_items = []
    for item in items:
        references = source_references_for_item(item)
        if references:
            column_items.append(source_column_item(item))
            wide_items.extend(
                source_url_item(item, reference, include_marker=index == 0)
                for index, reference in enumerate(references)
            )
            continue
        column_items.append(item)
    return column_items, wide_items


def source_references_for_item(item):
    row = item.get('row')
    if item.get('kind') != 'source' or not row:
        return []
    return source_reference_values(row)


def source_column_item(item):
    clone = dict(item)
    clone['text'] = format_source(item['row'], include_url=False)
    return clone


def source_url_item(item, reference, include_marker=False):
    return {
        'kind': 'source-url',
        'marker': item.get('marker') if include_marker else None,
        'text': reference,
        'row': item.get('row'),
    }


def measure_wide_annotation_items_height(items, width, style, label_style):
    height = 0
    for item in items:
        height += measure_wide_annotation_item_height(item, width, style, label_style)
        height += wide_annotation_item_gap()
    return height


def wide_annotation_item_gap():
    return 0.02 * inch


def measure_wide_annotation_item_height(item, width, style, label_style):
    marker_width = measure_marker_width(item.get('marker'), style)
    first_line_width = width - marker_width if item.get('marker') else width
    return len(wrap_marker_text(item.get('text') or '', first_line_width, width, style)) * style.leading


def measure_commentary_item_height(item, width, style, label_style):
    if item['kind'] == 'definition':
        label = item.get('label') or ''
        body = item.get('text') or ''
        label_text = f'{label} - ' if label else ''
        label_width = measure_string(label_text, label_style.bold_font, style.size, label_style.char_spacing)
        if label_text and label_width < width * 0.75:
            first_width = max(1, width - label_width)
            lines = wrap_annotation_text(body, first_width, style.font, style.size, style.char_spacing)
            remaining = rewrap_annotation_lines(lines[1:], width, style) if len(lines) > 1 else []
            return (1 + len(remaining)) * style.leading
        label_lines = 1 if label_text else 0
        body_lines = len(wrap_annotation_text(body, width, style.font, style.size, style.char_spacing))
        return (label_lines + body_lines) * style.leading
    marker_width = measure_marker_width(item.get('marker'), style)
    first_line_width = width - marker_width if item.get('marker') else width
    return len(wrap_marker_text(item.get('text') or '', first_line_width, width, style)) * style.leading


def measure_section_heading_height(layout):
    return layout.rule_margin_above + layout.rule_margin_below


def annotation_text_style(layout):
    return TextStyle(font=layout.annotation_font,
                     bold_font=bold_font_for(layout.annotation_font),
                     size=layout.annotation_font_size,
                     leading=layout.annotation_font_size * layout.annotation_line_spacing,
                     char_spacing=layout.annotation_kerning,
                     color=grayscale_color(layout.annotation_gray))


def measure_string(text, font, size, char_spacing=0):
    text = str(text or '')
    base_width = pdfmetrics.stringWidth(text, font, size)
    spacing_width = max(0, len(text) - 1) * (char_spacing or 0)
    return max(0, base_width + spacing_width)


def draw_text(pdf, x, y, text, font, size, color, char_spacing=0):
    pdf.setFillColor(color)
    text_object = pdf.beginText(x, y)
    text_object.setFont(font, size)
    text_object.setCharSpace(char_spacing or 0)
    text_object.textLine(str(text or ''))
    pdf.drawText(text_object)


def draw_export_header(pdf, data, layout, y):
    if page_has_body_chapter_title(data):
        return y
    width, _ = layout.page_size
    text = data.chapter or data.book.title
    font = font_variant_for(layout.chapter_font, layout.chapter_bold, layout.chapter_italic)
    text_width = measure_string(text, font, layout.chapter_font_size, layout.chapter_kerning)
    draw_text(
        pdf, (width - text_width) / 2, y, text, font,
        layout.chapter_font_size, grayscale_color(layout.chapter_gray), layout.chapter_kerning,
    )
    return y - layout.header_gap


def page_has_body_chapter_title(data):
    return any(
        (fmt.content_role or 'body') in ('title', 'chapter')
        for fmt in data.format_map.values()
    )


def draw_book_and_definitions(pdf, data, layout, y):
    width, _ = layout.page_size
    text_on_left = is_inside_text_left(data)
    left_margin, right_margin = page_margins(layout, text_on_left)
    content_width = width - left_margin - right_margin
    text_width = content_width if layout.one_column_top else (content_width - layout.column_gutter) * layout.text_ratio
    side_width = 0 if layout.one_column_top else content_width - layout.column_gutter - text_width
    left = left_margin
    if layout.one_column_top:
        text_x = left
        side_x = None
    elif text_on_left:
        text_x = left
        side_x = left + text_width + layout.column_gutter
    else:
        side_x = left
        text_x = left + side_width + layout.column_gutter

    text_style = TextStyle(font=layout.book_font, bold_font=bold_font_for(layout.book_font),
                           size=layout.book_font_size, leading=layout.book_font_size * layout.book_line_spacing,
                           char_spacing=layout.book_kerning,
                           color=grayscale_color(layout.book_gray),
                           role_styles=layout.content_role_styles)
    side_style = TextStyle(font=layout.definition_font, bold_font=bold_font_for(layout.definition_font),
                           size=layout.definition_font_size,
                           leading=layout.definition_font_size * layout.definition_line_spacing,
                           char_spacing=layout.definition_kerning,
                           color=grayscale_color(layout.definition_gray))
    title_style = TextStyle(font=bold_font_for(layout.definition_font), bold_font=bold_font_for(layout.definition_font),
                            size=layout.definition_font_size,
                            leading=layout.definition_font_size * layout.definition_line_spacing,
                            char_spacing=layout.definition_kerning,
                            color=grayscale_color(layout.definition_gray))

    text_height = measure_paragraph_block(data.paragraphs, text_width, text_style,
                                          text_layout=layout.text_layout)
    definition_items = format_definitions(sort_definitions_alpha(data.definitions))
    side_height = 0 if layout.one_column_top else measure_labeled_items(definition_items, side_width, side_style, title_style)
    block_height = max(layout.top_min_height, text_height, side_height)

    draw_paragraph_block(pdf, data.paragraphs, text_x, y, text_width, text_style,
                         text_layout=layout.text_layout, alignment=layout.book_alignment)
    if not layout.one_column_top:
        draw_labeled_items(pdf, definition_items, side_x, y, side_width, side_style, title_style,
                           empty_text='No definitions for this page.', alignment=layout.definition_alignment)
    return y - block_height


def draw_annotation_sections(pdf, data, layout, y):
    return draw_commentary_columns(pdf, data, layout, y)


def draw_commentary_columns(pdf, data, layout, y):
    items = []
    if layout.one_column_top:
        items.extend(format_definition_commentary_items(sort_definitions_alpha(data.definitions)))
    items.extend(format_commentary(data.commentary))
    if not items:
        return y
    y = ensure_space(pdf, layout, y, 1.0 * inch)
    y = draw_section_heading(pdf, None, layout, y, data=data)
    data.annotation_top_y = y

    column_count = max(1, min(4, int(layout.commentary_columns or 3)))
    gap = layout.commentary_column_gutter
    left, right, width = annotation_bounds(layout, data)
    column_width = (width - (gap * (column_count - 1))) / column_count
    style = TextStyle(font=layout.commentary_font, bold_font=bold_font_for(layout.commentary_font),
                      size=layout.commentary_font_size,
                      leading=layout.commentary_font_size * layout.commentary_line_spacing,
                      char_spacing=layout.commentary_kerning,
                      color=grayscale_color(layout.commentary_gray))
    marker_style = TextStyle(font=bold_font_for(layout.commentary_font),
                             bold_font=bold_font_for(layout.commentary_font),
                             size=max(5.5, layout.commentary_font_size - 0.8), leading=8,
                             char_spacing=layout.commentary_kerning,
                             color=grayscale_color(layout.commentary_gray))
    column_items, wide_items = split_wide_annotation_items(items, column_width, style)
    wide_height = measure_wide_annotation_items_height(wide_items, width, style, marker_style)
    data.annotation_column_bottom_y = annotation_column_bottom_limit(layout, wide_height)
    allocated_columns, _ = allocate_annotation_columns(
        column_items, column_width, column_count,
        max(0, y - data.annotation_column_bottom_y),
        style, marker_style,
    )
    if allocated_columns and allocated_columns[0].get('flow'):
        column_bottoms = draw_flowing_annotation_columns(
            pdf, allocated_columns[0]['items'], left, gap, y, column_width,
            style, marker_style, layout, data,
        )
    else:
        column_bottoms = []
        for column_index, column in enumerate(allocated_columns):
            column_y = y
            column_x = left + ((column_width + gap) * column_index)
            flow_column = [{'x': column_x}]
            for item in column['items']:
                if item['kind'] == 'definition':
                    column_y, _, _ = draw_definition_flow_item(
                        pdf, item['label'], item['text'], flow_column, 0, column_y, column_width,
                        style, marker_style, layout, data,
                    )
                else:
                    column_y, _, _ = draw_marker_flow_item(
                        pdf, item['marker'], item['text'], flow_column, 0, column_y, column_width,
                        style, marker_style, layout, data,
                        layout.commentary_alignment if item['kind'] == 'commentary' else layout.annotation_alignment,
                    )
                column_y -= annotation_column_item_gap()
            column_bottoms.append(column_y)
    y = min(column_bottoms, default=y)
    if wide_items:
        y = min(y, draw_wide_annotation_items_at_footer(pdf, wide_items, left, width, style, marker_style, layout))
    if hasattr(data, 'annotation_column_bottom_y'):
        delattr(data, 'annotation_column_bottom_y')
    return y


def draw_flowing_annotation_columns(pdf, items, left, gap, y, column_width, style, marker_style, layout, data):
    column_count = max(1, min(4, int(layout.commentary_columns or 3)))
    columns = [
        {'x': left + ((column_width + gap) * column_index)}
        for column_index in range(column_count)
    ]
    column_y = y
    column_index = 0
    column_bottoms = [y for _ in columns]
    prefer_clean_item_starts = flowing_annotation_column_heights(
        items, column_width, column_count,
        y - getattr(data, 'annotation_column_bottom_y', layout.bottom_margin),
        style, marker_style, prefer_clean_item_starts=True,
    ) is not None
    previous_item_spilled = False
    for item in items:
        if prefer_clean_item_starts and should_start_annotation_item_in_next_column(
            item, column_y, y, column_width, style, marker_style, layout, data, column_index, column_count,
            previous_item_spilled,
        ):
            column_y, column_index, columns = advance_annotation_column(pdf, layout, data, columns, column_index)
        start_column = column_index
        if item['kind'] == 'definition':
            column_y, column_index, _ = draw_definition_flow_item(
                pdf, item['label'], item['text'], columns, column_index, column_y, column_width,
                style, marker_style, layout, data,
            )
        else:
            column_y, column_index, _ = draw_marker_flow_item(
                pdf, item['marker'], item['text'], columns, column_index, column_y, column_width,
                style, marker_style, layout, data,
                layout.commentary_alignment if item['kind'] == 'commentary' else layout.annotation_alignment,
            )
        column_y -= annotation_column_item_gap()
        for filled_index in range(column_index):
            column_bottoms[filled_index] = getattr(data, 'annotation_column_bottom_y', layout.bottom_margin)
        column_bottoms[column_index] = min(column_bottoms[column_index], column_y)
        previous_item_spilled = column_index > start_column
    return column_bottoms


def should_start_annotation_item_in_next_column(item, y, top_y, column_width, style, label_style, layout, data,
                                                column_index, column_count, previous_item_spilled=False):
    if column_index >= column_count - 1 or y == top_y or not previous_item_spilled:
        return False
    bottom_y = getattr(data, 'annotation_column_bottom_y', layout.bottom_margin)
    item_height = measure_commentary_item_height(item, column_width, style, label_style) + annotation_column_item_gap()
    return item_height <= top_y - bottom_y


def annotation_column_bottom_limit(layout, wide_height):
    if wide_height <= 0:
        return layout.bottom_margin
    return footer_url_block_bottom_y(layout) + wide_height + footer_url_block_top_gap()


def footer_url_block_top_gap():
    return 0.14 * inch


def footer_url_block_bottom_y(layout):
    page_number_leading = layout.page_number_font_size * layout.page_number_line_spacing
    return layout.page_number_gap + page_number_leading + 0.08 * inch


def draw_wide_annotation_items_at_footer(pdf, items, x, width, style, marker_style, layout):
    height = measure_wide_annotation_items_height(items, width, style, marker_style)
    y = footer_url_block_bottom_y(layout) + height
    return draw_wide_annotation_items(pdf, items, x, y, width, style, marker_style, layout)


def draw_wide_annotation_items(pdf, items, x, y, width, style, marker_style, layout):
    for item in items:
        if y - style.leading < footer_url_block_bottom_y(layout):
            return y
        y = draw_wide_marker_item(
            pdf, item.get('marker'), item.get('text') or '', x, y, width,
            style, marker_style,
        )
        y -= wide_annotation_item_gap()
    return y


def draw_wide_marker_item(pdf, marker, text, x, y, width, style, marker_style):
    marker_width = measure_marker_width(marker, style)
    first_line_width = width - marker_width if marker else width
    lines = wrap_marker_text(text, first_line_width, width, style)
    for index, line in enumerate(lines):
        line_x = x
        line_width = width
        if index == 0 and marker:
            draw_superscript(pdf, marker, x, y, marker_style)
            line_x += marker_width
            line_width = first_line_width
        draw_aligned_plain_line(pdf, line, line_x, y, line_width, style, 'left')
        y -= style.leading
    return y


def advance_annotation_column(pdf, layout, data, columns, column_index):
    column_index += 1
    if column_index < len(columns):
        return getattr(data, 'annotation_top_y', layout.page_size[1] - layout.top_margin), column_index, columns
    return getattr(data, 'annotation_column_bottom_y', layout.bottom_margin), len(columns) - 1, columns


def ensure_annotation_line_space(pdf, layout, data, columns, column_index, y):
    bottom_limit = getattr(data, 'annotation_column_bottom_y', layout.bottom_margin)
    if y - layout.commentary_font_size >= bottom_limit:
        return y, column_index, columns
    return advance_annotation_column(pdf, layout, data, columns, column_index)


def draw_marker_flow_item(pdf, marker, text, columns, column_index, y, width, style, marker_style, layout, data,
                          alignment='left'):
    marker_width = measure_marker_width(marker, style)
    first_line_width = width - marker_width if marker else width
    lines = wrap_marker_text(text, first_line_width, width, style)
    marker_pending = bool(marker)

    for index, line in enumerate(lines):
        y, column_index, columns = ensure_annotation_line_space(pdf, layout, data, columns, column_index, y)
        line_x = columns[column_index]['x']
        line_width = width
        if marker_pending:
            draw_superscript(pdf, marker, line_x, y, marker_style)
            line_x += marker_width
            line_width = first_line_width
            marker_pending = False
        draw_aligned_plain_line(
            pdf, line, line_x, y, line_width, style,
            alignment_for_line(alignment, is_last=index == len(lines) - 1),
        )
        y -= style.leading
    return y, column_index, columns


def draw_definition_flow_item(pdf, label, text, columns, column_index, y, width, style, label_style, layout, data):
    label = label or ''
    body = text or ''
    label_text = f'{label} - ' if label else ''
    label_width = measure_string(label_text, label_style.bold_font, style.size, label_style.char_spacing)

    if label_text and label_width < width * 0.75:
        first_width = max(1, width - label_width)
        lines = wrap_annotation_text(body, first_width, style.font, style.size, style.char_spacing)
        if not lines:
            lines = ['']
        y, column_index, columns = ensure_annotation_line_space(pdf, layout, data, columns, column_index, y)
        line_x = columns[column_index]['x']
        draw_text(pdf, line_x, y, label_text, label_style.bold_font, style.size, style.color, label_style.char_spacing)
        draw_aligned_plain_line(pdf, lines[0], line_x + label_width, y, first_width, style, 'left')
        y -= style.leading
        remaining_lines = rewrap_annotation_lines(lines[1:], width, style) if len(lines) > 1 else []
    else:
        remaining_lines = wrap_annotation_text(body, width, style.font, style.size, style.char_spacing)
        if label_text:
            y, column_index, columns = ensure_annotation_line_space(pdf, layout, data, columns, column_index, y)
            draw_text(pdf, columns[column_index]['x'], y, label, label_style.bold_font, style.size, style.color,
                      label_style.char_spacing)
            y -= style.leading

    for index, line in enumerate(remaining_lines):
        y, column_index, columns = ensure_annotation_line_space(pdf, layout, data, columns, column_index, y)
        draw_aligned_plain_line(
            pdf, line, columns[column_index]['x'], y, width, style,
            alignment_for_line(layout.definition_alignment, is_last=index == len(remaining_lines) - 1),
        )
        y -= style.leading
    return y, column_index, columns


def draw_aligned_plain_line(pdf, line, x, y, width, style, alignment='left'):
    if alignment == 'justify':
        draw_justified_line(pdf, line, x, y, width, style)
        return
    line_width = measure_string(line, style.font, style.size, style.char_spacing)
    draw_text(pdf, aligned_x(x, width, line_width, alignment), y, line, style.font, style.size,
              style.color, style.char_spacing)


def draw_section_heading(pdf, heading, layout, y, data=None):
    left, right, width = annotation_bounds(layout, data) if data else (
        layout.annotation_margin,
        layout.annotation_margin,
        layout.page_size[0] - (2 * layout.annotation_margin),
    )
    if heading:
        pdf.setFont('Helvetica-Bold', 10)
        pdf.setFillColor(colors.HexColor('#263640'))
        pdf.drawString(left, y, heading.upper())
    line_y = y - layout.rule_margin_above
    pdf.setStrokeColor(colors.HexColor('#c8d0d7'))
    pdf.line(left, line_y, layout.page_size[0] - right, line_y)
    return line_y - layout.rule_margin_below


def format_definitions(lookups):
    return [(lk.entry.word_phrase or '', lk.entry.meaning or '') for lk in lookups if lk.entry]


def format_definition_commentary_items(lookups):
    return [{'kind': 'definition', 'label': word, 'text': meaning} for word, meaning in format_definitions(lookups)]


def format_commentary(rows):
    return [{'kind': kind, 'marker': marker, 'text': annotation_note_text(kind, row), 'row': row} for marker, kind, row in rows]


def format_references(rows):
    return [format_reference(row) for row in rows]


def format_reference(row):
    target = row.target_book.title if row.target_book else 'Book'
    loc = make_location(row.target_chapter, row.target_page, row.target_paragraph, row.target_verse)
    text = f'{target}'
    if loc:
        text = f'{text} ({loc})'
    if row.quoted_text:
        text = f'{text}: "{row.quoted_text}"'
    if row.comments:
        text = f'{text} - {row.comments}'
    return text


def format_sources(rows):
    return [format_source(row) for row in rows]


def format_source(row, include_url=True):
    bits = [row.name or 'Source']
    if row.author:
        bits.append(f'by {row.author}')
    if row.publication:
        bits.append(row.publication)
    if include_url:
        bits.extend(source_reference_values(row))
    if row.notes:
        bits.append(row.notes)
    return ' - '.join(bits)


def source_reference_values(row):
    values = []
    seen = set()
    for entry in sorted(getattr(row, 'urls', []) or [], key=lambda item: (item.sort_order or 0, item.id or 0)):
        reference = (entry.url or '').strip()
        if reference and reference not in seen:
            values.append(reference)
            seen.add(reference)
    legacy_url = (getattr(row, 'url', None) or '').strip()
    if legacy_url and legacy_url not in seen:
        values.insert(0, legacy_url)
    return values


def make_location(chapter, page, paragraph, verse):
    parts = []
    if chapter:
        parts.append(f'Ch {chapter}')
    if page:
        parts.append(f'p. {page}')
    if paragraph:
        parts.append(f'para. {paragraph}')
    if verse:
        parts.append(f'verse {verse}')
    return ', '.join(parts)


def is_inside_text_left(data_or_page):
    relative = getattr(data_or_page, 'relative_page_number', None)
    if relative is not None:
        return int(relative) % 2 == 1
    page = getattr(data_or_page, 'page', data_or_page)
    try:
        return int(str(page)) % 2 == 1
    except (TypeError, ValueError):
        return True


def page_margins(layout, text_on_left):
    if text_on_left:
        return layout.inside_margin, layout.outside_margin
    return layout.outside_margin, layout.inside_margin


def annotation_bounds(layout, data):
    if not data:
        left = right = layout.annotation_margin
    else:
        left, right = page_margins(layout, is_inside_text_left(data))
    return left, right, layout.page_size[0] - left - right


def draw_footer(pdf, data, layout):
    width, _ = layout.page_size
    font = font_variant_for(layout.page_number_font, layout.page_number_bold, layout.page_number_italic)
    text_width = measure_string(data.page, font, layout.page_number_font_size,
                                layout.page_number_kerning)
    draw_text(
        pdf, (width - text_width) / 2, layout.page_number_gap, data.page,
        font, layout.page_number_font_size,
        grayscale_color(layout.page_number_gray), layout.page_number_kerning,
    )


def grayscale_color(percent):
    try:
        value = max(0, min(90, float(percent))) / 100
    except (TypeError, ValueError):
        value = 0
    return colors.Color(value, value, value)


def bold_font_for(font):
    if font == 'Times-Roman':
        return 'Times-Bold'
    if font == 'Courier':
        return 'Courier-Bold'
    return 'Helvetica-Bold'


def font_variant_for(font, is_bold=False, is_italic=False):
    if font == 'Times-Roman':
        if is_bold and is_italic:
            return 'Times-BoldItalic'
        if is_bold:
            return 'Times-Bold'
        if is_italic:
            return 'Times-Italic'
        return 'Times-Roman'
    if font == 'Courier':
        if is_bold and is_italic:
            return 'Courier-BoldOblique'
        if is_bold:
            return 'Courier-Bold'
        if is_italic:
            return 'Courier-Oblique'
        return 'Courier'
    if is_bold and is_italic:
        return 'Helvetica-BoldOblique'
    if is_bold:
        return 'Helvetica-Bold'
    if is_italic:
        return 'Helvetica-Oblique'
    return 'Helvetica'


def token_font_for(token, style):
    role = token.get('content_role') or 'body'
    role_style = style.role_styles.get(role, {})
    is_bold = token.get('is_bold') or bool(role_style.get('bold'))
    is_italic = token.get('is_italic') or bool(role_style.get('italic'))
    return font_variant_for(role_style.get('font') or style.font, is_bold, is_italic)


def token_size_for(token, style):
    role = token.get('content_role') or 'body'
    role_style = style.role_styles.get(role, {})
    return float(role_style.get('size') or style.size)


def token_char_spacing_for(token, style):
    role = token.get('content_role') or 'body'
    role_style = style.role_styles.get(role, {})
    return float(role_style.get('kerning') if role_style.get('kerning') is not None else style.char_spacing)


def token_color_for(token, style):
    role = token.get('content_role') or 'body'
    role_style = style.role_styles.get(role, {})
    if role_style.get('gray') is not None:
        return grayscale_color(role_style.get('gray'))
    return style.color


def token_leading_for(token, style):
    size = token_size_for(token, style)
    role = token.get('content_role') or 'body'
    role_style = style.role_styles.get(role, {})
    return size * float(role_style.get('line_spacing') or (style.leading / style.size))


def alignment_for_line(alignment, is_last=False):
    if alignment == 'justify' and not is_last:
        return 'justify'
    if alignment == 'center':
        return 'center'
    if alignment == 'right':
        return 'right'
    return 'left'


def aligned_x(x, width, text_width, alignment):
    if alignment == 'center':
        return x + max(0, width - text_width) / 2
    if alignment == 'right':
        return x + max(0, width - text_width)
    return x


def draw_box(pdf, x, y, width, height, fill):
    pdf.setFillColor(fill)
    pdf.setStrokeColor(colors.HexColor('#d4d8dd'))
    pdf.rect(x, y, width, height, fill=1, stroke=1)


def measure_paragraph_block(paragraphs, width, style, text_layout='reflow_justified'):
    if not paragraphs:
        return style.leading
    height = 0
    for paragraph in paragraphs:
        if text_layout == 'preserve_lines':
            height += sum(segment_leading(segment, style) for segment in paragraph)
        elif paragraph_has_role(paragraph, 'poetry'):
            for segment in paragraph:
                if segment_has_role(segment, 'poetry'):
                    height += segment_leading(segment, style)
                else:
                    height += sum(
                        line_leading(line, style)
                        for line in wrap_word_tokens(paragraph_tokens([segment]), width, style)
                    )
        else:
            height += sum(line_leading(line, style) for line in wrap_word_tokens(paragraph_tokens(paragraph), width, style))
        height += style.leading * 0.35
    return height


def measure_labeled_items(items, width, body_style, label_style):
    if not items:
        return body_style.leading * 2
    height = 0
    for label, body in items:
        height += label_style.leading
        height += len(wrap_text(body, width, body_style.font, body_style.size,
                                body_style.char_spacing)) * body_style.leading
        height += body_style.leading * 0.55
    return height


def measure_text_height(text, width, font, size, leading, char_spacing=0):
    return len(wrap_text(text, width, font, size, char_spacing)) * leading


def draw_paragraph_block(pdf, paragraphs, x, y, width, style, text_layout='reflow_justified', alignment='justify',
                         force_alignment=None):
    if not paragraphs:
        return draw_wrapped_text(pdf, 'No book text stored for this page.', x, y, width, style)
    preserve_lines = text_layout == 'preserve_lines'
    for paragraph in paragraphs:
        if not preserve_lines and paragraph_has_role(paragraph, 'poetry'):
            y = draw_poetry_aware_paragraph(pdf, paragraph, x, y, width, style, alignment=alignment,
                                            force_alignment=force_alignment)
            y -= style.leading * 0.35
            continue
        if not preserve_lines:
            y = draw_justified_paragraph(pdf, paragraph, x, y, width, style, alignment=alignment,
                                         force_alignment=force_alignment)
            y -= style.leading * 0.35
            continue
        for index, segment in enumerate(paragraph):
            y = draw_original_text_line(
                pdf, segment, x, y, width, style,
                justify=True, force_alignment=force_alignment,
            )
        y -= style.leading * 0.35
    return y


def draw_poetry_aware_paragraph(pdf, paragraph, x, y, width, style, alignment='justify', force_alignment=None):
    for segment in paragraph:
        if segment_has_role(segment, 'poetry'):
            y = draw_original_text_line(pdf, segment, x, y, width, style, justify=False,
                                        force_alignment=force_alignment)
        else:
            y = draw_justified_paragraph(pdf, [segment], x, y, width, style, alignment=alignment,
                                         force_alignment=force_alignment)
    return y


def draw_justified_paragraph(pdf, paragraph, x, y, width, style, alignment='justify', force_alignment=None):
    tokens = paragraph_tokens(paragraph)
    lines = wrap_word_tokens(tokens, width, style)
    for index, line in enumerate(lines):
        line_alignment = force_alignment or role_alignment_for_line(line, style) or alignment_for_line(alignment, is_last=index == len(lines) - 1)
        draw_token_line(pdf, line, x, y, width, style, alignment=line_alignment)
        y -= line_leading(line, style)
    return y


def role_alignment_for_line(tokens, style):
    overrides = {
        token.get('alignment_override')
        for token in tokens
        if token.get('type') != 'space' and token.get('alignment_override')
    }
    if len(overrides) == 1:
        return alignment_for_line(next(iter(overrides)))
    if len(overrides) > 1:
        return None
    roles = {token.get('content_role') for token in tokens if token.get('type') != 'space'}
    if len(roles) != 1:
        return None
    role = next(iter(roles)) or 'body'
    role_style = style.role_styles.get(role, {})
    alignment = role_style.get('alignment')
    if alignment in ('left', 'center', 'right', 'justify'):
        return alignment_for_line(alignment)
    return None


def paragraph_tokens(paragraph, preserve_hyphen=False):
    tokens = []
    previous_text = ''
    for segment in paragraph:
        for fragment in segment.get('fragments', []):
            text = (fragment.get('text') or '').strip()
            if not text:
                continue
            words = text.split()
            if not words:
                continue
            if tokens and previous_text and not previous_text.endswith('-'):
                tokens.append({'type': 'space'})
            markers = fragment.get('markers', [])
            for word_index, word in enumerate(words):
                word_text = word if preserve_hyphen else (word[:-1] if word.endswith('-') else word)
                tokens.append({
                    'type': 'word',
                    'text': word_text,
                    'markers': markers if word_index == 0 else [],
                    'is_bold': bool(fragment.get('is_bold')),
                    'is_italic': bool(fragment.get('is_italic')),
                    'content_role': fragment.get('content_role') or 'body',
                    'alignment_override': fragment.get('alignment_override') or '',
                })
                if word_index < len(words) - 1:
                    tokens.append({'type': 'space'})
            previous_text = text
    return tokens


def wrap_word_tokens(tokens, width, style):
    lines = []
    current = []
    current_width = 0
    pending_space = False
    space_width = measure_string(' ', style.font, style.size, style.char_spacing)
    for token in tokens:
        if token.get('type') == 'space':
            pending_space = bool(current)
            continue
        token_width = word_token_width(token, style)
        prefix_width = space_width if pending_space else 0
        if current and current_width + prefix_width + token_width > width:
            lines.append(current)
            current = []
            current_width = 0
            pending_space = False
            prefix_width = 0
        if pending_space and current:
            current.append({'type': 'space'})
            current_width += space_width
        current.append(token)
        current_width += token_width
        pending_space = False
    if current:
        lines.append(current)
    return lines


def draw_token_line(pdf, tokens, x, y, width, style, alignment='left'):
    gap_count = sum(1 for token in tokens if token.get('type') == 'space')
    base_width = sum(token_width(token, style) for token in tokens)
    justify = alignment == 'justify'
    extra_gap = max(0, (width - base_width) / gap_count) if justify and gap_count else 0
    cursor_x = aligned_x(x, width, base_width, alignment)
    for token in tokens:
        if token.get('type') == 'space':
            cursor_x += measure_string(' ', style.font, style.size, style.char_spacing) + extra_gap
            continue
        for marker in token.get('markers', []):
            draw_inline_marker(pdf, marker, cursor_x, y, style)
            cursor_x += inline_marker_advance(marker, style)
        token_font = token_font_for(token, style)
        token_size = token_size_for(token, style)
        token_spacing = token_char_spacing_for(token, style)
        draw_text(pdf, cursor_x, y, token.get('text', ''), token_font, token_size,
                  token_color_for(token, style), token_spacing)
        cursor_x += measure_string(token.get('text', ''), token_font, token_size, token_spacing)


def line_leading(tokens, style):
    word_tokens = [token for token in tokens if token.get('type') != 'space']
    if not word_tokens:
        return style.leading
    return max(token_leading_for(token, style) for token in word_tokens)


def segment_leading(segment, style):
    return line_leading(segment_tokens(segment), style)


def paragraph_has_role(paragraph, role):
    return any(segment_has_role(segment, role) for segment in paragraph)


def segment_has_role(segment, role):
    return any((fragment.get('content_role') or 'body') == role for fragment in segment.get('fragments', []))


def token_width(token, style):
    if token.get('type') == 'space':
        return measure_string(' ', style.font, style.size, style.char_spacing)
    return word_token_width(token, style)


def word_token_width(token, style):
    marker_width = sum(inline_marker_advance(marker, style) for marker in token.get('markers', []))
    return marker_width + measure_string(token.get('text', ''), token_font_for(token, style),
                                         token_size_for(token, style),
                                         token_char_spacing_for(token, style))


def draw_original_text_line(pdf, segment, x, y, width, style, justify=False, force_alignment=None):
    tokens = segment_tokens(segment)
    if force_alignment:
        draw_token_line(pdf, tokens, x, y, width, style, alignment=force_alignment)
        return y - segment_leading(segment, style)
    line_alignment = segment_alignment(segment, style)
    if line_alignment:
        draw_token_line(pdf, tokens, x, y, width, style, alignment=line_alignment)
        return y - segment_leading(segment, style)
    if justify:
        if draw_justified_original_tokens(pdf, tokens, x, y, width, style):
            return y - segment_leading(segment, style)

    cursor_x = x
    previous_text = ''
    for fragment in segment.get('fragments', []):
        text = fragment.get('text') or ''
        prefix = ''
        if previous_text and not previous_text.endswith('-'):
            prefix = ' '
        if prefix:
            draw_text(pdf, cursor_x, y, prefix, style.font, style.size, style.color, style.char_spacing)
            cursor_x += measure_string(prefix, style.font, style.size, style.char_spacing)
        for marker in fragment.get('markers', []):
            draw_inline_marker(pdf, marker, cursor_x, y, style)
            cursor_x += inline_marker_advance(marker, style)
        role = fragment.get('content_role') or 'body'
        role_style = style.role_styles.get(role, {})
        fragment_size = float(role_style.get('size') or style.size)
        fragment_spacing = float(role_style.get('kerning') if role_style.get('kerning') is not None else style.char_spacing)
        fragment_font = font_variant_for(
            role_style.get('font') or style.font,
            fragment.get('is_bold') or bool(role_style.get('bold')),
            fragment.get('is_italic') or bool(role_style.get('italic')),
        )
        draw_text(pdf, cursor_x, y, text, fragment_font, fragment_size,
                  grayscale_color(role_style.get('gray')) if role_style.get('gray') is not None else style.color,
                  fragment_spacing)
        cursor_x += measure_string(text, fragment_font, fragment_size, fragment_spacing)
        previous_text = text
    return y - segment_leading(segment, style)


def segment_tokens(segment):
    return paragraph_tokens([segment], preserve_hyphen=True)


def segment_alignment(segment, style):
    tokens = segment_tokens(segment)
    return role_alignment_for_line(tokens, style)


def segment_has_markers(segment):
    return any(fragment.get('markers') for fragment in segment.get('fragments', []))


def draw_guarded_justified_line(pdf, line, x, y, width, style):
    if not should_justify_line(line, width, style):
        return False
    draw_justified_line(pdf, line, x, y, width, style)
    return True


def draw_guarded_justified_tokens(pdf, tokens, x, y, width, style):
    if not should_justify_tokens(tokens, width, style):
        return False
    draw_token_line(pdf, tokens, x, y, width, style, alignment='justify')
    return True


def draw_justified_original_tokens(pdf, tokens, x, y, width, style):
    if not should_justify_original_tokens(tokens, width, style):
        return False
    draw_token_line(pdf, tokens, x, y, width, style, alignment='justify')
    return True


def should_justify_line(line, width, style):
    gaps = line.count(' ')
    if gaps <= 1:
        return False
    line_width = measure_string(line, style.font, style.size, style.char_spacing)
    extra = width - line_width
    if extra <= 0:
        return False
    return True


def should_justify_tokens(tokens, width, style):
    gaps = sum(1 for token in tokens if token.get('type') == 'space')
    if gaps <= 1:
        return False
    line_width = sum(token_width(token, style) for token in tokens)
    extra = width - line_width
    if extra <= 0:
        return False
    return True


def should_justify_original_tokens(tokens, width, style):
    gaps = sum(1 for token in tokens if token.get('type') == 'space')
    if gaps <= 0:
        return False
    line_width = sum(token_width(token, style) for token in tokens)
    return width - line_width > 0


def draw_inline_marker(pdf, marker, x, y, style):
    number = marker.get('number')
    if not number:
        return
    marker_style = TextStyle(font='Helvetica-Bold', bold_font='Helvetica-Bold',
                             size=max(5.8, style.size - 3), leading=style.leading)
    draw_superscript(pdf, number, x, y, marker_style)


def inline_marker_advance(marker, style):
    number = marker.get('number')
    if not number:
        return 0
    marker_size = max(5.8, style.size - 3)
    return pdfmetrics.stringWidth(str(number), 'Helvetica-Bold', marker_size) + 1.5


def best_marker_phrase(commentary_text, line_text):
    normalized_line = normalize_match_text(line_text)
    words = commentary_text.split()
    for count in range(min(8, len(words)), 1, -1):
        phrase = ' '.join(words[:count])
        if phrase in normalized_line:
            return phrase
    return ''


def marker_text_offset(line_text, normalized_phrase, style):
    start = phrase_start_index(line_text, normalized_phrase)
    if start <= 0:
        return 0
    return measure_string(line_text[:start], style.font, style.size, style.char_spacing)


def phrase_start_index(line_text, normalized_phrase):
    phrase_words = normalized_phrase.split()
    if not phrase_words:
        return 0
    word_matches = list(re.finditer(r'\S+', line_text))
    line_words = [normalize_match_text(match.group(0)) for match in word_matches]
    for index in range(0, len(line_words) - len(phrase_words) + 1):
        if line_words[index:index + len(phrase_words)] == phrase_words:
            return word_matches[index].start()
    return 0


def draw_wrapped_text_with_marker(pdf, text, x, y, width, style, marker=None, marker_style=None, justify=False, alignment='left'):
    marker_width = measure_marker_width(marker, style)
    marker_style = marker_style or TextStyle(font='Helvetica-Bold', bold_font='Helvetica-Bold',
                                             size=max(5.8, style.size - 3), leading=style.leading,
                                             color=style.color)
    first_line_width = width - marker_width if marker_width else width
    lines = wrap_text(text, first_line_width, style.font, style.size, style.char_spacing)
    for index, line in enumerate(lines):
        line_x = x
        line_width = width
        if index == 0 and marker:
            draw_superscript(pdf, marker, x, y, marker_style)
            line_x = x + marker_width
            line_width = first_line_width
        is_last = index == len(lines) - 1
        line_alignment = alignment_for_line('justify' if justify else alignment, is_last=is_last)
        if line_alignment == 'justify':
            draw_justified_line(pdf, line, line_x, y, line_width, style)
        else:
            line_text_width = measure_string(line, style.font, style.size, style.char_spacing)
            draw_text(pdf, aligned_x(line_x, line_width, line_text_width, line_alignment), y, line,
                      style.font, style.size, style.color, style.char_spacing)
        y -= style.leading
    return y


def draw_superscript(pdf, marker, x, y, marker_style):
    pdf.setFillColor(marker_style.color)
    pdf.setFont(marker_style.bold_font, marker_style.size)
    pdf.drawString(x, y + 4, str(marker))


def measure_marker_width(marker, style):
    if not marker:
        return 0
    marker_size = max(5.8, style.size - 3)
    return pdfmetrics.stringWidth(str(marker), 'Helvetica-Bold', marker_size) + 3


def draw_labeled_items(pdf, items, x, y, width, body_style, label_style, empty_text='', alignment='left'):
    if not items:
        return y
    for label, body in items:
        draw_text(pdf, x, y, shorten(label, width=34, placeholder='...'), label_style.bold_font,
                  label_style.size, label_style.color, label_style.char_spacing)
        y -= label_style.leading
        y = draw_wrapped_text(pdf, body, x, y, width, body_style, alignment=alignment)
        y -= body_style.leading * 0.55
    return y


def draw_wrapped_text(pdf, text, x, y, width, style, justify=False, alignment='left'):
    lines = wrap_text(text, width, style.font, style.size, style.char_spacing)
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        line_alignment = alignment_for_line('justify' if justify else alignment, is_last=is_last)
        if line_alignment == 'justify':
            draw_justified_line(pdf, line, x, y, width, style)
        else:
            line_width = measure_string(line, style.font, style.size, style.char_spacing)
            draw_text(pdf, aligned_x(x, width, line_width, line_alignment), y, line,
                      style.font, style.size, style.color, style.char_spacing)
        y -= style.leading
    return y


def draw_justified_line(pdf, line, x, y, width, style):
    gaps = line.count(' ')
    if gaps <= 0:
        draw_text(pdf, x, y, line, style.font, style.size, style.color, style.char_spacing)
        return
    line_width = measure_string(line, style.font, style.size, style.char_spacing)
    extra = max(0, width - line_width)
    text = pdf.beginText(x, y)
    text.setFont(style.font, style.size)
    text.setCharSpace(style.char_spacing or 0)
    text.setWordSpace(extra / gaps)
    text.textLine(line)
    pdf.drawText(text)


def wrap_text(text, width, font, size, char_spacing=0):
    words = str(text or '').split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = word if not current else f'{current} {word}'
        if measure_string(candidate, font, size, char_spacing) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def wrap_annotation_text(text, width, font, size, char_spacing=0):
    wrapped = []
    for segment in annotation_text_lines(text):
        if segment == '':
            wrapped.append('')
        else:
            wrapped.extend(wrap_text(segment, width, font, size, char_spacing))
    return wrapped or ['']


def rewrap_annotation_lines(lines, width, style):
    return wrap_annotation_text('\n'.join(lines), width, style.font, style.size, style.char_spacing)


def wrap_marker_text(text, first_width, full_width, style):
    wrapped = []
    first_line = True
    for segment in annotation_text_lines(text):
        if segment == '':
            wrapped.append('')
            first_line = False
            continue
        lines = wrap_text_with_first_width(segment, first_width if first_line else full_width,
                                           full_width, style)
        wrapped.extend(lines)
        first_line = False
    return wrapped or ['']


def annotation_text_lines(text):
    return str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')


def wrap_text_with_first_width(text, first_width, full_width, style):
    words = str(text or '').split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        limit = first_width if not lines else full_width
        candidate = word if not current else f'{current} {word}'
        if measure_string(candidate, style.font, style.size, style.char_spacing) <= limit:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def ensure_space(pdf, layout, y, needed):
    if y - needed >= layout.bottom_margin:
        return y
    return y

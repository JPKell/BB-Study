from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re
from textwrap import shorten

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from ..models import (Book, BookContent, BookContentFormat, BookLocation, BookReference,
                      Commentary, ContentTopic, DictionaryLookup, Source)


@dataclass
class TextStyle:
    font: str = 'Times-Roman'
    bold_font: str = 'Times-Bold'
    size: float = 10
    leading: float = 14
    char_spacing: float = 0
    color: colors.Color = colors.black


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
    chapter: str
    paragraphs: list
    definitions: list
    commentary: list
    commentary_markers: dict
    references: list
    sources: list
    topics: list


def export_page_pdf(book_id, page, layout=None):
    """Return PDF bytes for one book page and its annotations."""
    layout = layout or ExportLayout()
    data = collect_page_export_data(book_id, page)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=layout.page_size)
    render_page_export(pdf, data, layout)
    pdf.save()
    buffer.seek(0)
    return buffer


def export_pages_pdf(book_id, pages, layout=None):
    """Return PDF bytes for multiple book pages in one PDF."""
    layout = layout or ExportLayout()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=layout.page_size)
    for index, page in enumerate(pages):
        if index:
            pdf.showPage()
        data = collect_page_export_data(book_id, page)
        render_page_export(pdf, data, layout)
    pdf.save()
    buffer.seek(0)
    return buffer


def collect_page_export_data(book_id, page):
    book = Book.query.get_or_404(book_id)
    rows = (BookContent.query
            .filter_by(book_id=book_id, page=page)
            .order_by(BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id)
            .all())
    chapter = next((r.chapter_name or r.chapter for r in rows if r.chapter_name or r.chapter), '')
    commentary = (Commentary.query
                  .filter_by(book_id=book_id, page=page)
                  .order_by(Commentary.created_at)
                  .all())
    commentary = sort_commentary_by_text_order(rows, commentary)
    commentary_items, commentary_markers = build_commentary_markers(commentary)
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

    topics = collect_page_topics(rows)
    format_map = collect_content_formats(book_id, page)
    paragraphs = build_marked_page_paragraphs(rows, commentary_markers, format_map)
    return PageExportData(book, str(page), chapter, paragraphs, definitions,
                          commentary_items, commentary_markers, references, sources, topics)


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
    markers = {}
    items = []
    for index, row in enumerate(commentary, start=1):
        marker = {
            'number': index,
            'line_text': normalize_match_text(row.commentary_text),
        }
        markers.setdefault(location_key(row.paragraph, row.verse), []).append(marker)
        markers.setdefault(paragraph_key(row.paragraph), []).append((row.verse, marker))
        items.append((index, row))
    return items, markers


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


def collect_page_topics(rows):
    if not rows:
        return []
    page_low_id = min(row.id for row in rows)
    page_high_id = max(row.id for row in rows)
    topics = []
    for link in ContentTopic.query.order_by(ContentTopic.created_at).all():
        start_id = link.start_content_id or link.book_content_id
        end_id = link.end_content_id or link.book_content_id
        if not start_id or not end_id:
            continue
        low_id = min(start_id, end_id)
        high_id = max(start_id, end_id)
        if low_id <= page_high_id and high_id >= page_low_id:
            topics.append(link)
    return topics


def render_page_export(pdf, data, layout):
    width, height = layout.page_size
    y = height - layout.top_margin
    y = draw_export_header(pdf, data, layout, y)
    y = draw_book_and_definitions(pdf, data, layout, y)
    y -= layout.section_gap
    y = draw_annotation_sections(pdf, data, layout, y)
    draw_footer(pdf, data, layout)


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
    width, _ = layout.page_size
    text = data.chapter or data.book.title
    text_width = measure_string(text, layout.chapter_font, layout.chapter_font_size, layout.chapter_kerning)
    draw_text(
        pdf, (width - text_width) / 2, y, text, layout.chapter_font,
        layout.chapter_font_size, grayscale_color(layout.chapter_gray), layout.chapter_kerning,
    )
    return y - layout.header_gap


def draw_book_and_definitions(pdf, data, layout, y):
    width, _ = layout.page_size
    text_on_left = is_inside_text_left(data.page)
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
                           color=grayscale_color(layout.book_gray))
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
    definition_items = format_definitions(data.definitions)
    side_height = 0 if layout.one_column_top else measure_labeled_items(definition_items, side_width, side_style, title_style)
    block_height = max(layout.top_min_height, text_height, side_height)

    draw_paragraph_block(pdf, data.paragraphs, text_x, y, text_width, text_style,
                         text_layout=layout.text_layout, alignment=layout.book_alignment)
    if not layout.one_column_top:
        draw_labeled_items(pdf, definition_items, side_x, y, side_width, side_style, title_style,
                           empty_text='No definitions for this page.', alignment=layout.definition_alignment)
    return y - block_height


def draw_annotation_sections(pdf, data, layout, y):
    y = draw_commentary_columns(pdf, data, layout, y)
    sections = [
        ('Book references', format_references(data.references)),
        ('Other references', format_sources(data.sources)),
        ('Topic tags', format_topics(data.topics)),
    ]
    for heading, items in sections:
        if not items:
            continue
        y = ensure_space(pdf, layout, y, 0.7 * inch)
        y = draw_section_heading(pdf, heading, layout, y, data=data)
        left, right, width = annotation_bounds(layout, data)
        annotation_style = TextStyle(font=layout.annotation_font,
                                     bold_font=bold_font_for(layout.annotation_font),
                                     size=layout.annotation_font_size,
                                     leading=layout.annotation_font_size * layout.annotation_line_spacing,
                                     char_spacing=layout.annotation_kerning,
                                     color=grayscale_color(layout.annotation_gray))
        for item in items:
            estimated_height = measure_text_height(item, width, annotation_style.font,
                                                   annotation_style.size, annotation_style.leading,
                                                   annotation_style.char_spacing)
            y = ensure_space(pdf, layout, y, estimated_height + 0.2 * inch)
            y = draw_wrapped_text(pdf, item, left, y, width, annotation_style)
            y -= 0.08 * inch
    return y


def draw_commentary_columns(pdf, data, layout, y):
    items = []
    if layout.one_column_top:
        items.extend(format_definition_commentary_items(data.definitions))
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
    columns = [{'x': left + ((column_width + gap) * i)} for i in range(column_count)]
    column_index = 0

    for item in items:
        if item['kind'] == 'definition':
            y, column_index, columns = draw_definition_flow_item(
                pdf, item['label'], item['text'], columns, column_index, y, column_width,
                style, marker_style, layout, data,
            )
        else:
            y, column_index, columns = draw_marker_flow_item(
                pdf, item['marker'], item['text'], columns, column_index, y, column_width,
                style, marker_style, layout, data,
            )
        y -= 0.12 * inch
        if y < layout.bottom_margin:
            y, column_index, columns = advance_annotation_column(pdf, layout, data, columns, column_index)
    return y


def advance_annotation_column(pdf, layout, data, columns, column_index):
    column_index += 1
    if column_index < len(columns):
        return getattr(data, 'annotation_top_y', layout.page_size[1] - layout.top_margin), column_index, columns
    pdf.showPage()
    y = layout.page_size[1] - layout.top_margin
    y = draw_section_heading(pdf, None, layout, y, data=data)
    data.annotation_top_y = y
    return y, 0, columns


def ensure_annotation_line_space(pdf, layout, data, columns, column_index, y):
    if y - layout.commentary_font_size >= layout.bottom_margin:
        return y, column_index, columns
    return advance_annotation_column(pdf, layout, data, columns, column_index)


def draw_marker_flow_item(pdf, marker, text, columns, column_index, y, width, style, marker_style, layout, data):
    marker_width = measure_marker_width(marker, style)
    first_line_width = width - marker_width if marker else width
    lines = wrap_text(text, first_line_width, style.font, style.size, style.char_spacing)
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
            alignment_for_line(layout.commentary_alignment, is_last=index == len(lines) - 1),
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
        lines = wrap_text(body, first_width, style.font, style.size, style.char_spacing)
        if not lines:
            lines = ['']
        y, column_index, columns = ensure_annotation_line_space(pdf, layout, data, columns, column_index, y)
        line_x = columns[column_index]['x']
        draw_text(pdf, line_x, y, label_text, label_style.bold_font, style.size, style.color, label_style.char_spacing)
        draw_aligned_plain_line(pdf, lines[0], line_x + label_width, y, first_width, style, 'left')
        y -= style.leading
        remaining_lines = wrap_text(' '.join(lines[1:]), width, style.font, style.size, style.char_spacing) if len(lines) > 1 else []
    else:
        remaining_lines = wrap_text(body, width, style.font, style.size, style.char_spacing)
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
    return [{'kind': 'commentary', 'marker': marker, 'text': row.commentary_text or ''} for marker, row in rows]


def format_references(rows):
    items = []
    for row in rows:
        target = row.target_book.title if row.target_book else 'Book'
        loc = make_location(row.target_chapter, row.target_page, row.target_paragraph, row.target_verse)
        text = f'{target}'
        if loc:
            text = f'{text} ({loc})'
        if row.quoted_text:
            text = f'{text}: "{row.quoted_text}"'
        if row.comments:
            text = f'{text} - {row.comments}'
        items.append(text)
    return items


def format_sources(rows):
    items = []
    for row in rows:
        bits = [row.name or 'Source']
        if row.source_type:
            bits.append(row.source_type)
        if row.author:
            bits.append(f'by {row.author}')
        if row.publication:
            bits.append(row.publication)
        if row.url:
            bits.append(row.url)
        if row.notes:
            bits.append(row.notes)
        items.append(' - '.join(bits))
    return items


def format_topics(rows):
    items = []
    for link in rows:
        topic = link.topic.name if link.topic else 'Topic'
        note = f' - {link.notes}' if link.notes else ''
        items.append(f'{topic}{note}')
    return items


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


def is_inside_text_left(page):
    try:
        return int(str(page)) % 2 == 1
    except ValueError:
        return True


def page_margins(layout, text_on_left):
    if text_on_left:
        return layout.inside_margin, layout.outside_margin
    return layout.outside_margin, layout.inside_margin


def annotation_bounds(layout, data):
    if not data:
        left = right = layout.annotation_margin
    else:
        left, right = page_margins(layout, is_inside_text_left(data.page))
    return left, right, layout.page_size[0] - left - right


def draw_footer(pdf, data, layout):
    width, _ = layout.page_size
    text_width = measure_string(data.page, layout.page_number_font, layout.page_number_font_size,
                                layout.page_number_kerning)
    draw_text(
        pdf, (width - text_width) / 2, layout.page_number_gap, data.page,
        layout.page_number_font, layout.page_number_font_size,
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
    return font_variant_for(style.font, token.get('is_bold'), token.get('is_italic'))


def alignment_for_line(alignment, is_last=False):
    if alignment == 'justify' and not is_last:
        return 'justify'
    if alignment == 'center':
        return 'center'
    return 'left'


def aligned_x(x, width, text_width, alignment):
    if alignment == 'center':
        return x + max(0, width - text_width) / 2
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
            height += len(paragraph) * style.leading
        else:
            height += len(wrap_word_tokens(paragraph_tokens(paragraph), width, style)) * style.leading
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


def draw_paragraph_block(pdf, paragraphs, x, y, width, style, text_layout='reflow_justified', alignment='justify'):
    if not paragraphs:
        return draw_wrapped_text(pdf, 'No book text stored for this page.', x, y, width, style)
    preserve_lines = text_layout == 'preserve_lines'
    for paragraph in paragraphs:
        if not preserve_lines:
            y = draw_justified_paragraph(pdf, paragraph, x, y, width, style, alignment=alignment)
            y -= style.leading * 0.35
            continue
        for index, segment in enumerate(paragraph):
            y = draw_original_text_line(
                pdf, segment, x, y, width, style,
                justify=True,
            )
        y -= style.leading * 0.35
    return y


def draw_justified_paragraph(pdf, paragraph, x, y, width, style, alignment='justify'):
    tokens = paragraph_tokens(paragraph)
    lines = wrap_word_tokens(tokens, width, style)
    for index, line in enumerate(lines):
        line_alignment = alignment_for_line(alignment, is_last=index == len(lines) - 1)
        draw_token_line(pdf, line, x, y, width, style, alignment=line_alignment)
        y -= style.leading
    return y


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
        draw_text(pdf, cursor_x, y, token.get('text', ''), token_font, style.size, style.color, style.char_spacing)
        cursor_x += measure_string(token.get('text', ''), token_font, style.size, style.char_spacing)


def token_width(token, style):
    if token.get('type') == 'space':
        return measure_string(' ', style.font, style.size, style.char_spacing)
    return word_token_width(token, style)


def word_token_width(token, style):
    marker_width = sum(inline_marker_advance(marker, style) for marker in token.get('markers', []))
    return marker_width + measure_string(token.get('text', ''), token_font_for(token, style), style.size,
                                         style.char_spacing)


def draw_original_text_line(pdf, segment, x, y, width, style, justify=False):
    if justify:
        tokens = segment_tokens(segment)
        if draw_justified_original_tokens(pdf, tokens, x, y, width, style):
            return y - style.leading

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
        fragment_font = font_variant_for(style.font, fragment.get('is_bold'), fragment.get('is_italic'))
        draw_text(pdf, cursor_x, y, text, fragment_font, style.size, style.color, style.char_spacing)
        cursor_x += measure_string(text, fragment_font, style.size, style.char_spacing)
        previous_text = text
    return y - style.leading


def segment_tokens(segment):
    return paragraph_tokens([segment], preserve_hyphen=True)


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
        return draw_wrapped_text(pdf, empty_text, x, y, width, body_style, alignment=alignment)
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


def ensure_space(pdf, layout, y, needed):
    if y - needed >= layout.bottom_margin:
        return y
    pdf.showPage()
    return layout.page_size[1] - layout.top_margin

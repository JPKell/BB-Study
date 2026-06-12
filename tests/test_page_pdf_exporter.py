"""Unit tests for page PDF export layout helpers."""

from app.services.page_pdf_exporter import (
    ExportLayout,
    TextStyle,
    allocate_annotation_columns,
    display_export_text,
    measure_paragraph_block,
    measure_commentary_item_height,
    measure_string,
    paragraph_tokens,
    prune_bottom_annotations,
    wrap_text,
    wrap_word_tokens,
)


class AnnotationRow:
    def __init__(self, row_id, text, rank):
        self.id = row_id
        self.commentary_text = text
        self.rank = rank
        self.created_at = None
        self.paragraph = 1
        self.verse = 1


class PageData:
    def __init__(self, commentary_rows):
        self.commentary_rows = commentary_rows
        self.reflect_rows = []
        self.references = []
        self.sources = []
        self.definitions = []
        self.relative_page_number = 1


def test_long_commentary_can_flow_across_columns():
    style = TextStyle(font='Helvetica', bold_font='Helvetica-Bold', size=7, leading=8.96)
    long_text = ' '.join([
        'Today, A.A. operates in more than 180 countries around the world.',
        'Because of the anonymous nature of the program, membership can only be estimated,',
        'but current estimates place membership at more than two million people worldwide.',
        'A.A. has often been called the largest organization whose members never wanted to join.',
        'There are more than 123,000 A.A. groups around the world, and A.A. literature has',
        'been translated into over 100 languages.',
        'Through these groups and publications, the message of recovery continues to reach',
        'people across cultures, languages, and borders.',
    ] * 2)
    items = [
        {'kind': 'commentary', 'marker': 1, 'text': long_text},
        {'kind': 'commentary', 'marker': 2, 'text': 'Bill W. and Dr. Bob founded AA.'},
        {'kind': 'commentary', 'marker': 3, 'text': 'A short third comment.'},
    ]
    column_width = 140
    available = 180

    long_height = measure_commentary_item_height(items[0], column_width, style, style)
    columns, fits = allocate_annotation_columns(items, column_width, 3, available, style, style)

    assert long_height > available
    assert fits
    assert columns[0]['flow'] is True
    assert columns[0]['items'] == items
    assert columns[2]['height'] > 0
    assert max(column['height'] for column in columns) <= available


def test_half_letter_pruning_tries_next_commentary_rank_when_first_is_too_long():
    long_text = ' '.join([
        'Today AA operates in more than one hundred eighty countries around the world',
        'and continues to carry the message through groups and publications across',
        'cultures languages and borders.',
    ] * 2)
    rows = [
        AnnotationRow(1, long_text, 1),
        AnnotationRow(2, 'A short fallback comment should still fit.', 2),
    ]
    data = PageData(rows)
    layout = ExportLayout(
        page_size=(5.5 * 72, 8.5 * 72),
        inside_margin=0.8 * 72,
        outside_margin=0.45 * 72,
        commentary_column_gutter=0.32 * 72,
        commentary_columns=3,
    )
    y = layout.bottom_margin + layout.rule_margin_above + layout.rule_margin_below + 45

    prune_bottom_annotations(data, layout, y)

    assert data.commentary_rows == [rows[1]]


def test_content_role_margins_are_measured_around_matching_paragraphs():
    style = TextStyle(
        font='Times-Roman',
        bold_font='Times-Bold',
        size=10,
        leading=12,
        role_styles={'title': {'margin_above': 18, 'margin_below': 24}},
    )
    paragraph = [{
        'fragments': [{
            'text': 'Chapter title',
            'markers': [],
            'content_role': 'title',
        }],
    }]

    height = measure_paragraph_block([paragraph], 200, style)

    assert height == 18 + 12 + (12 * 0.35) + 24


def test_aa_initials_do_not_split_when_wrapping_export_text():
    font = 'Times-Roman'
    size = 10
    width = measure_string('A. A.', font, size)

    lines = wrap_text('A. A. is here', width, font, size)

    assert display_export_text(lines[0]) == 'A.\u00a0A.'


def test_aa_initials_stay_in_one_book_text_token():
    style = TextStyle(font='Times-Roman', bold_font='Times-Bold', size=10, leading=12)
    paragraph = [{
        'fragments': [{
            'text': 'A. A. is here',
            'markers': [],
            'content_role': 'body',
        }],
    }]
    width = measure_string('A. A.', style.font, style.size)

    lines = wrap_word_tokens(paragraph_tokens(paragraph), width, style)

    assert display_export_text(lines[0][0]['text']) == 'A.\u00a0A.'

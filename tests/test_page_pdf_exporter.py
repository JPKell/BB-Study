"""Unit tests for page PDF export layout helpers."""

from types import SimpleNamespace

from app.services.page_pdf_exporter import (
    ExportLayout,
    TextStyle,
    allocate_annotation_columns,
    apply_annotation_numbering_state,
    build_annotation_markers,
    build_marked_page_paragraphs,
    display_export_text,
    measure_paragraph_block,
    measure_commentary_item_height,
    measure_string,
    paragraph_tokens,
    prune_bottom_annotations,
    update_annotation_numbering_state,
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


def test_numbering_state_counts_only_annotations_kept_on_prior_page():
    kept_note = AnnotationRow(1, 'Placed note.', 1)
    next_note = AnnotationRow(3, 'Next page note.', 1)
    content_row = SimpleNamespace(paragraph=1, verse=1)
    numbering_state = {}

    first_page = SimpleNamespace(
        chapter='Chapter One',
        commentary_marker_start=1,
        content_rows=[content_row],
        commentary_rows=[kept_note],
        references=[],
        sources=[],
    )
    update_annotation_numbering_state(first_page, numbering_state)

    next_page = SimpleNamespace(
        chapter='Chapter One',
        commentary_marker_start=3,
        content_rows=[content_row],
        commentary_rows=[next_note],
        references=[],
        sources=[],
        format_map={},
    )
    apply_annotation_numbering_state(next_page, numbering_state)

    assert next_page.commentary_marker_start == 2
    assert next_page.commentary[0][0] == 2


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


def test_reflow_preserves_hyphen_at_end_of_wrapped_line():
    paragraph = [{
        'fragments': [{
            'text': 'well-',
            'markers': [],
            'content_role': 'body',
        }],
    }]

    tokens = [token for token in paragraph_tokens(paragraph) if token.get('type') == 'word']

    assert tokens[0]['text'] == 'well-'


def test_reflow_removes_single_split_hyphen_between_fragments():
    paragraph = [
        {'fragments': [{'text': 'com-', 'markers': [], 'content_role': 'body'}]},
        {'fragments': [{'text': 'munity', 'markers': [], 'content_role': 'body'}]},
    ]

    tokens = paragraph_tokens(paragraph)

    assert [token['text'] for token in tokens if token.get('type') == 'word'] == ['com', 'munity']
    assert all(token.get('type') != 'space' for token in tokens)


def test_reflow_reduces_double_hyphen_to_preserved_single_hyphen():
    paragraph = [
        {'fragments': [{'text': 'well--', 'markers': [], 'content_role': 'body'}]},
        {'fragments': [{'text': 'being', 'markers': [], 'content_role': 'body'}]},
        {'fragments': [{'text': 'A--B', 'markers': [], 'content_role': 'body'}]},
    ]

    tokens = paragraph_tokens(paragraph)

    assert [token['text'] for token in tokens if token.get('type') == 'word'] == ['well-', 'being', 'A-B']
    assert tokens[1].get('type') != 'space'


def test_inline_marker_is_attached_after_sentence_text():
    paragraph = [{
        'fragments': [{
            'text': 'First sentence.',
            'markers': [{'number': 7}],
            'content_role': 'body',
        }],
    }]

    tokens = [token for token in paragraph_tokens(paragraph) if token.get('type') == 'word']

    assert tokens[0]['markers'] == []
    assert tokens[-1]['after_markers'] == [{'number': 7}]


def test_inline_marker_waits_for_end_of_wrapped_verse():
    rows = [
        SimpleNamespace(id=1, paragraph=1, line=1, verse=1, content='First part of a'),
        SimpleNamespace(id=2, paragraph=1, line=2, verse=1, content='wrapped sentence.'),
    ]
    markers = {(1, 1): [{'number': 7}], ('paragraph', 1): [(1, {'number': 7})]}

    paragraph = build_marked_page_paragraphs(rows, markers)[0]
    tokens = [token for token in paragraph_tokens(paragraph) if token.get('type') == 'word']

    assert all(token['after_markers'] == [] for token in tokens[:-1])
    assert tokens[-1]['after_markers'] == [{'number': 7}]


def test_annotation_markers_can_start_after_prior_chapter_notes():
    first = AnnotationRow(1, 'Earlier note.', None)
    second = AnnotationRow(2, 'Current note.', None)

    items, markers = build_annotation_markers(
        [('commentary', first), ('commentary', second)],
        start=4,
    )

    assert [item[0] for item in items] == [4, 5]
    assert [marker['number'] for marker in markers[(1, 1)]] == [4, 5]

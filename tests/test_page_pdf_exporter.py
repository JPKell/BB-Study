"""Unit tests for page PDF export layout helpers."""

from app.services.page_pdf_exporter import (
    TextStyle,
    allocate_annotation_columns,
    measure_commentary_item_height,
)


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

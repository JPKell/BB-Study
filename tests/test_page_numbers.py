"""Unit tests for page number helpers."""

from app.page_numbers import _relative_page_mapping_preserving_existing
from app.routes.main import book_export_pages_from_relative_map


def test_relative_mapping_preserves_existing_page_numbers():
    mapping = _relative_page_mapping_preserving_existing(
        ['i', 'ii', '1', '2'],
        {'i': 10, '1': 25},
    )

    assert mapping['i'] == 10
    assert mapping['1'] == 25


def test_relative_mapping_fills_missing_without_reusing_existing_numbers():
    mapping = _relative_page_mapping_preserving_existing(
        ['i', 'ii', '1', '2'],
        {'ii': 1},
    )

    assert mapping['ii'] == 1
    assert mapping['i'] == 2
    assert len(set(mapping.values())) == len(mapping)


def test_book_export_pages_can_include_start_blank_for_odd_first_relative():
    pages = book_export_pages_from_relative_map({1: '1', 2: '2'}, include_start_blank=True)

    assert pages == [None, '1', '2']


def test_book_export_pages_can_start_with_text_for_duplex_printing():
    pages = book_export_pages_from_relative_map({1: '1', 2: '2'}, include_start_blank=False)

    assert pages == ['1', '2']


def test_book_export_pages_can_filter_by_relative_page_range():
    pages = book_export_pages_from_relative_map(
        {1: 'i', 2: 'ii', 3: '1', 4: '2'},
        include_start_blank=False,
        start_relative=2,
        end_relative=3,
    )

    assert pages == ['ii', '1']


def test_book_export_pages_returns_empty_for_out_of_bounds_relative_page_range():
    pages = book_export_pages_from_relative_map(
        {1: '1', 2: '2'},
        include_start_blank=True,
        start_relative=5,
        end_relative=8,
    )

    assert pages == []

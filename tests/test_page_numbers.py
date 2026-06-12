"""Unit tests for page number helpers."""

from app.page_numbers import _relative_page_mapping_preserving_existing


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

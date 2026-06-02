"""Unit tests for app.services.pamphlet_importer."""

import json
import pytest

from app import create_app, db
from app.models import Pamphlet, PamphletContent
from app.services.pamphlet_importer import (
    _normalize_text,
    _get_page_label,
    _get_series,
    _derive_title,
    _build_content_rows,
    import_pamphlet_json,
)


# ---------------------------------------------------------------------------
# Minimal JSON fixture helpers
# ---------------------------------------------------------------------------

def _make_doc(filename, pages, metadata_title=None):
    return {
        'filename': filename,
        'path_in_zip': filename,
        'metadata_title': metadata_title,
        'page_count': len(pages),
        'extraction_stats': {},
        'pages': pages,
    }


def _make_page(relative, printed=None, detected=False, sections=None, boxed=None, note=None):
    page = {
        'relative_page_number': relative,
        'printed_page_number': printed if printed is not None else relative,
        'printed_page_number_detected': detected,
        'sections': sections or [],
        'boxed_sections': boxed or [],
    }
    if note:
        page['extraction_note'] = note
    return page


def _make_json(documents):
    return {
        'source_zip': 'test.zip',
        'extraction_notes': {},
        'documents': documents,
        'extraction_summary': {},
    }


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with application.app_context():
        db.create_all()
        yield application


@pytest.fixture
def json_file(tmp_path):
    """Factory: write a dict to a temp JSON file and return the path."""
    def _write(data):
        p = tmp_path / 'pamphlets.json'
        p.write_text(json.dumps(data), encoding='utf-8')
        return str(p)
    return _write


# ---------------------------------------------------------------------------
# Unit tests – pure helpers (no DB)
# ---------------------------------------------------------------------------

class TestNormalizeText:
    def test_strips_whitespace(self):
        assert _normalize_text('  hello  ') == 'hello'

    def test_normalizes_crlf(self):
        assert _normalize_text('a\r\nb') == 'a\nb'

    def test_collapses_triple_newlines(self):
        assert _normalize_text('a\n\n\nb') == 'a\n\nb'

    def test_collapses_multiple_spaces(self):
        assert _normalize_text('a  b\t c') == 'a b c'

    def test_empty_string(self):
        assert _normalize_text('') == ''

    def test_none_returns_empty(self):
        assert _normalize_text(None) == ''


class TestGetPageLabel:
    def test_uses_printed_when_detected(self):
        page = {'printed_page_number': 'iii', 'printed_page_number_detected': True,
                'relative_page_number': 3}
        assert _get_page_label(page) == 'iii'

    def test_uses_relative_when_not_detected(self):
        page = {'printed_page_number': 3, 'printed_page_number_detected': False,
                'relative_page_number': 3}
        assert _get_page_label(page) == '3'

    def test_integer_printed_converted_to_string(self):
        page = {'printed_page_number': 12, 'printed_page_number_detected': True,
                'relative_page_number': 14}
        assert _get_page_label(page) == '12'


class TestGetSeries:
    def test_standard_prefix(self):
        assert _get_series('P-11_AA_Member.pdf') == 'P-11'

    def test_smf_prefix(self):
        assert _get_series('SMF-127_The_AA_Preamble.pdf') == 'SMF-127'

    def test_b_prefix(self):
        assert _get_series('B-28_AA_Older_Alcoholic_LARGE.pdf') == 'B-28'


class TestDeriveTitle:
    def test_uses_metadata_title_when_present(self):
        doc = {'filename': 'P-1_This_Is_AA.pdf', 'metadata_title': 'This Is AA'}
        assert _derive_title(doc) == 'This Is AA'

    def test_derives_from_filename_when_no_metadata(self):
        doc = {'filename': 'P-1_This_Is_AA.pdf', 'metadata_title': None}
        assert _derive_title(doc) == 'This Is AA'


# ---------------------------------------------------------------------------
# Integration tests – require DB
# ---------------------------------------------------------------------------

class TestBuildContentRows:
    def test_header_paragraph_is_zero(self, app):
        with app.app_context():
            pages = [_make_page(1, sections=[{'header': 'Chapter 1', 'text': 'Body text.'}])]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            header_rows = [r for r in rows if r.content_mode == 'header']
            assert len(header_rows) == 1
            assert header_rows[0].paragraph == 0
            assert header_rows[0].content == 'Chapter 1'

    def test_body_paragraphs_increment(self, app):
        with app.app_context():
            text = 'First paragraph.\n\nSecond paragraph.'
            pages = [_make_page(1, sections=[{'header': None, 'text': text}])]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            body_rows = [r for r in rows if r.content_mode == 'page']
            assert len(body_rows) == 2
            assert body_rows[0].paragraph == 1
            assert body_rows[1].paragraph == 2

    def test_sidebar_continues_paragraph_counter(self, app):
        with app.app_context():
            pages = [_make_page(
                1,
                sections=[{'header': None, 'text': 'Main text.'}],
                boxed=[{'box_number': 1, 'bbox': [], 'sections': [
                    {'header': None, 'text': 'Sidebar text.'}
                ]}],
            )]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            body_rows = [r for r in rows if r.content_mode == 'page']
            sidebar_rows = [r for r in rows if r.content_mode == 'sidebar']
            assert body_rows[0].paragraph == 1
            assert sidebar_rows[0].paragraph == 2

    def test_sidebar_content_mode(self, app):
        with app.app_context():
            pages = [_make_page(
                1,
                boxed=[{'box_number': 1, 'bbox': [], 'sections': [
                    {'header': None, 'text': 'Sidebar.'}
                ]}],
            )]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            assert any(r.content_mode == 'sidebar' for r in rows)

    def test_warning_for_extraction_note(self, app):
        with app.app_context():
            pages = [_make_page(1, note='No extractable text found.')]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            warning_rows = [r for r in rows if r.content_mode == 'warning']
            assert len(warning_rows) == 1
            assert 'No extractable' in warning_rows[0].content

    def test_page_label_used(self, app):
        with app.app_context():
            pages = [_make_page(5, printed='iv', detected=True,
                                sections=[{'header': None, 'text': 'Text.'}])]
            doc = _make_doc('P-1_Test.pdf', pages, 'Test')
            rows = _build_content_rows(99, doc)
            assert all(r.page == 'iv' for r in rows)


class TestImportPamphletJson:
    def _write_json(self, tmp_path, data):
        p = tmp_path / 'pamphlets.json'
        p.write_text(json.dumps(data), encoding='utf-8')
        return str(p)

    def test_new_pamphlet_import(self, app, tmp_path):
        docs = [_make_doc('P-1_Test_Pamphlet.pdf',
                          [_make_page(1, sections=[{'header': 'H', 'text': 'Body.'}])],
                          'Test Pamphlet')]
        path = self._write_json(tmp_path, _make_json(docs))

        with app.app_context():
            result = import_pamphlet_json(path)
            assert result['pamphlets'] == 1
            assert result['errors'] == 0
            pamphlet = Pamphlet.query.filter_by(series='P-1').first()
            assert pamphlet is not None
            assert pamphlet.title == 'Test Pamphlet'
            assert PamphletContent.query.filter_by(pamphlet_id=pamphlet.id).count() > 0

    def test_update_existing_pamphlet(self, app, tmp_path):
        docs = [_make_doc('P-1_Test_Pamphlet.pdf',
                          [_make_page(1, sections=[{'header': None, 'text': 'Old content.'}])],
                          'Old Title')]
        path = self._write_json(tmp_path, _make_json(docs))

        with app.app_context():
            import_pamphlet_json(path)
            old_count = PamphletContent.query.join(Pamphlet).filter(Pamphlet.series == 'P-1').count()

        # Re-import with updated content
        docs2 = [_make_doc('P-1_Test_Pamphlet.pdf',
                           [_make_page(1, sections=[{'header': None, 'text': 'New content.'}]),
                            _make_page(2, sections=[{'header': None, 'text': 'Page 2.'}])],
                           'New Title')]
        sub = tmp_path / 'update'
        sub.mkdir()
        path2 = self._write_json(sub, _make_json(docs2))

        with app.app_context():
            result = import_pamphlet_json(path2)
            assert result['errors'] == 0
            pamphlet = Pamphlet.query.filter_by(series='P-1').first()
            assert pamphlet.title == 'New Title'
            rows = PamphletContent.query.filter_by(pamphlet_id=pamphlet.id).all()
            # Should have new rows, not old ones
            assert any('New content' in r.content for r in rows)
            assert not any('Old content' in r.content for r in rows)

    def test_rollback_on_failure_continues_remaining(self, app, tmp_path, monkeypatch):
        """A bad document should not prevent import of subsequent ones."""
        docs = [
            _make_doc('P-1_Good.pdf',
                      [_make_page(1, sections=[{'header': None, 'text': 'Good.'}])],
                      'Good Pamphlet'),
            _make_doc('P-2_Bad.pdf',
                      [_make_page(1, sections=[{'header': None, 'text': 'Bad.'}])],
                      'Bad Pamphlet'),
            _make_doc('P-3_AlsoGood.pdf',
                      [_make_page(1, sections=[{'header': None, 'text': 'Also good.'}])],
                      'Also Good'),
        ]
        path = self._write_json(tmp_path, _make_json(docs))

        # Make the second pamphlet fail during content build
        original_build = __import__(
            'app.services.pamphlet_importer', fromlist=['_build_content_rows']
        )._build_content_rows

        call_count = {'n': 0}

        def bad_build(pamphlet_id, doc):
            call_count['n'] += 1
            if call_count['n'] == 2:
                raise RuntimeError("Simulated failure")
            return original_build(pamphlet_id, doc)

        monkeypatch.setattr(
            'app.services.pamphlet_importer._build_content_rows', bad_build
        )

        with app.app_context():
            result = import_pamphlet_json(path)

        assert result['errors'] == 1
        assert result['pamphlets'] == 2  # P-1 and P-3 succeeded

    def test_page_numbering_uses_printed_when_detected(self, app, tmp_path):
        docs = [_make_doc('P-1_Test.pdf',
                          [_make_page(5, printed='iv', detected=True,
                                      sections=[{'header': None, 'text': 'Intro.'}])],
                          'Test')]
        path = self._write_json(tmp_path, _make_json(docs))
        with app.app_context():
            import_pamphlet_json(path)
            pamphlet = Pamphlet.query.filter_by(series='P-1').first()
            rows = PamphletContent.query.filter_by(pamphlet_id=pamphlet.id).all()
            assert all(r.page == 'iv' for r in rows)

    def test_header_import(self, app, tmp_path):
        docs = [_make_doc('P-1_Test.pdf',
                          [_make_page(1, sections=[{'header': 'Section Title', 'text': 'Body.'}])],
                          'Test')]
        path = self._write_json(tmp_path, _make_json(docs))
        with app.app_context():
            import_pamphlet_json(path)
            pamphlet = Pamphlet.query.filter_by(series='P-1').first()
            rows = PamphletContent.query.filter_by(
                pamphlet_id=pamphlet.id, content_mode='header'
            ).all()
            assert len(rows) == 1
            assert rows[0].paragraph == 0
            assert rows[0].content == 'Section Title'

    def test_sidebar_import(self, app, tmp_path):
        docs = [_make_doc('P-1_Test.pdf',
                          [_make_page(1,
                                      sections=[{'header': None, 'text': 'Main body.'}],
                                      boxed=[{'box_number': 1, 'bbox': [], 'sections': [
                                          {'header': None, 'text': 'Sidebar content.'}
                                      ]}])],
                          'Test')]
        path = self._write_json(tmp_path, _make_json(docs))
        with app.app_context():
            import_pamphlet_json(path)
            pamphlet = Pamphlet.query.filter_by(series='P-1').first()
            sidebar_rows = PamphletContent.query.filter_by(
                pamphlet_id=pamphlet.id, content_mode='sidebar'
            ).all()
            assert len(sidebar_rows) == 1
            assert sidebar_rows[0].content == 'Sidebar content.'
            # Sidebar paragraph counter continues from body
            body_rows = PamphletContent.query.filter_by(
                pamphlet_id=pamphlet.id, content_mode='page'
            ).all()
            assert sidebar_rows[0].paragraph > body_rows[-1].paragraph

import pytest
from flask import Flask

from app import db
from app.models import Book, BookContent, BookReference, Commentary, Source
from app.services.page_pdf_exporter import chapter_annotation_marker_start, collect_page_export_data


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def _content(book, page, verse, chapter='Chapter One'):
    return BookContent(
        book_id=book.id,
        content_mode='sentence',
        chapter_name=chapter,
        chapter=chapter,
        page=page,
        relative_page_number=int(page),
        paragraph=1,
        verse=verse,
        content=f'Page {page} verse {verse}.',
    )


def test_chapter_marker_start_counts_prior_page_notes(app):
    with app.app_context():
        book = Book(title='Test Book')
        db.session.add(book)
        db.session.flush()
        page_one = _content(book, '1', 1)
        page_two = _content(book, '2', 1)
        other_chapter = _content(book, '3', 1, chapter='Chapter Two')
        db.session.add_all([page_one, page_two, other_chapter])
        db.session.flush()
        db.session.add_all([
            Commentary(book_id=book.id, page='1', paragraph=1, verse=1, commentary_text='Earlier comment'),
            Source(book_id=book.id, page='1', paragraph=1, verse=1, name='Earlier source'),
            BookReference(source_book_id=book.id, source_page='1', source_paragraph=1, source_verse=1,
                          target_book_id=book.id, target_page='1', target_paragraph=1, target_verse=1),
            Commentary(book_id=book.id, page='2', paragraph=1, verse=1, commentary_text='Current comment'),
            Commentary(book_id=book.id, page='3', paragraph=1, verse=1, commentary_text='Other chapter comment'),
        ])
        db.session.commit()

        assert chapter_annotation_marker_start(book.id, '2', [page_two]) == 4
        data = collect_page_export_data(book.id, '2')

        assert data.commentary_marker_start == 4
        assert [item[0] for item in data.commentary] == [4]
        assert data.commentary_markers[(1, 1)][0]['number'] == 4

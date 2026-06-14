import pytest
from flask import Flask

from app import db
from app.models import (
    Book,
    BookContent,
    BookContentFormat,
    BookLocation,
    BookReference,
    Commentary,
    ReflectPrompt,
    Source,
)


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    from app.routes.api import api_bp
    application.register_blueprint(api_bp, url_prefix='/api')
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def _content(book, verse, content):
    return BookContent(
        book_id=book.id,
        content_mode='sentence',
        chapter_name='Chapter',
        chapter='Chapter',
        page='10',
        paragraph=1,
        verse=verse,
        content=content,
    )


def test_join_next_merges_and_renumbers_following_verses(app):
    with app.app_context():
        book = Book(title='Test Book')
        db.session.add(book)
        db.session.flush()
        first = _content(book, 1, 'First sentence.')
        second = _content(book, 2, 'Second sentence.')
        third = _content(book, 3, 'Third sentence.')
        db.session.add_all([first, second, third])
        db.session.flush()
        db.session.add_all([
            BookContentFormat(book_id=book.id, page='10', paragraph=1, verse=3, is_bold=True),
            Commentary(book_id=book.id, page='10', paragraph=1, verse=2, commentary_text='on joined'),
            ReflectPrompt(book_id=book.id, page='10', paragraph=1, verse=3, prompt_text='on shifted'),
            Source(book_id=book.id, page='10', paragraph=1, verse=3, name='Source'),
            BookReference(source_book_id=book.id, source_page='10', source_paragraph=1, source_verse=3,
                          target_book_id=book.id, target_page='10', target_paragraph=1, target_verse=2),
            BookLocation(book_id=book.id, page='10', paragraph=1, line_number=3, line_text='Third sentence.'),
        ])
        db.session.commit()

        response = app.test_client().post(f'/api/book-content/{first.id}/join-next', json={})

        assert response.status_code == 200
        rows = (BookContent.query
                .filter_by(book_id=book.id, page='10', paragraph=1)
                .order_by(BookContent.verse, BookContent.id)
                .all())
        assert [(row.verse, row.content) for row in rows] == [
            (1, 'First sentence. Second sentence.'),
            (2, 'Third sentence.'),
        ]
        assert Commentary.query.one().verse == 1
        assert ReflectPrompt.query.one().verse == 2
        assert Source.query.one().verse == 2
        assert BookReference.query.one().source_verse == 2
        assert BookReference.query.one().target_verse == 1
        assert BookLocation.query.one().line_number == 2
        assert BookContentFormat.query.one().verse == 2


def test_join_next_stays_inside_paragraph(app):
    with app.app_context():
        book = Book(title='Test Book')
        db.session.add(book)
        db.session.flush()
        first = _content(book, 1, 'Only sentence.')
        next_paragraph = _content(book, 1, 'Next paragraph.')
        next_paragraph.paragraph = 2
        db.session.add_all([first, next_paragraph])
        db.session.commit()

        response = app.test_client().post(f'/api/book-content/{first.id}/join-next', json={})

        assert response.status_code == 400
        assert response.get_json()['error'] == 'There is no following verse in this paragraph to join'

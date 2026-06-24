from pathlib import Path

import pytest
from flask import Flask

from app import db
from app.models import Book, BookContent, Setting
from app.routes.main import main_bp


@pytest.fixture
def app():
    app_dir = Path(__file__).resolve().parents[1] / 'app'
    application = Flask(
        __name__,
        template_folder=str(app_dir / 'templates'),
        static_folder=str(app_dir / 'static'),
    )
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['SECRET_KEY'] = 'test'
    db.init_app(application)
    application.register_blueprint(main_bp)

    with application.app_context():
        db.create_all()
        db.session.add(Setting(key='theme', value='dark'))
        db.session.commit()
        yield application
        db.session.remove()
        db.drop_all()


def _add_book_with_pages(*pages):
    book = Book(title='Test Book')
    db.session.add(book)
    db.session.flush()
    for relative_page, page in enumerate(pages, start=1):
        db.session.add(BookContent(
            book_id=book.id,
            content_mode='sentence',
            page=page,
            relative_page_number=relative_page,
            paragraph=1,
            verse=1,
            content=f'Page {page}',
        ))
    db.session.commit()
    return book


def test_reader_restores_last_page_after_a_fresh_visit(app):
    with app.app_context():
        book = _add_book_with_pages('1', '42')
        client = app.test_client()

        response = client.get(f'/?book_id={book.id}&page=42')
        assert response.status_code == 200

        response = client.get('/')

        assert response.status_code == 200
        assert b'id="pageInput"' in response.data
        assert b'value="42"' in response.data
        assert Setting.query.filter_by(key='current_book_id').one().value == str(book.id)
        assert Setting.query.filter_by(key='current_page').one().value == '42'
        assert Setting.query.filter_by(key=f'book_{book.id}_page').one().value == '42'


def test_restored_book_page_becomes_the_durable_current_page(app):
    with app.app_context():
        book = _add_book_with_pages('1', '42')
        db.session.add_all([
            Setting(key='current_book_id', value=str(book.id)),
            Setting(key='current_page', value='1'),
            Setting(key=f'book_{book.id}_page', value='42'),
        ])
        db.session.commit()

        response = app.test_client().get('/')

        assert response.status_code == 200
        assert b'value="42"' in response.data
        assert Setting.query.filter_by(key='current_page').one().value == '42'


def test_secondary_pane_cannot_overwrite_primary_position_for_same_book(app):
    with app.app_context():
        book = _add_book_with_pages('1', '42')
        db.session.add(Setting(key='current_secondary_book_id', value=str(book.id)))
        db.session.commit()
        client = app.test_client()

        response = client.get(f'/?book_id={book.id}&page=42')

        assert response.status_code == 200
        assert Setting.query.filter_by(key=f'book_{book.id}_page').one().value == '42'
        assert Setting.query.filter_by(key=f'secondary_book_{book.id}_page').one().value == '1'

        response = client.get('/')

        assert response.status_code == 200
        assert b'id="pageInput"' in response.data
        assert b'value="42"' in response.data
        assert Setting.query.filter_by(key=f'book_{book.id}_page').one().value == '42'

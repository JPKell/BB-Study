from flask import Blueprint, render_template, request, redirect, url_for
from ..models import Setting, Book, BookContent
from .. import db

main_bp = Blueprint('main', __name__)


def get_theme():
    s = Setting.query.filter_by(key='theme').first()
    return s.value if s else 'dark'


def get_current_book():
    s = Setting.query.filter_by(key='current_book_id').first()
    if s and s.value:
        return Book.query.get(int(s.value))
    return None


def get_current_page():
    s = Setting.query.filter_by(key='current_page').first()
    return s.value if s else '1'


# ── Reading page ──────────────────────────────────────────────────────────────

@main_bp.route('/')
def index():
    theme = get_theme()
    current_book = get_current_book()
    current_page = get_current_page()
    books = Book.query.order_by(Book.title).all()

    page_content = []
    if current_book:
        page_content = (BookContent.query
                        .filter_by(book_id=current_book.id, page=current_page)
                        .order_by(BookContent.paragraph, BookContent.line)
                        .all())

    return render_template('index.html',
                           theme=theme,
                           current_book=current_book,
                           current_page=current_page,
                           page_content=page_content,
                           books=books)


# ── Settings page ─────────────────────────────────────────────────────────────

@main_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    theme = get_theme()
    if request.method == 'POST':
        new_theme = request.form.get('theme', 'dark')
        s = Setting.query.filter_by(key='theme').first()
        if s:
            s.value = new_theme
        else:
            db.session.add(Setting(key='theme', value=new_theme))
        db.session.commit()
        return redirect(url_for('main.settings'))
    all_settings = Setting.query.order_by(Setting.key).all()
    return render_template('settings.html', theme=theme, all_settings=all_settings)


# ── Books ─────────────────────────────────────────────────────────────────────

@main_bp.route('/books')
def books():
    all_books = Book.query.order_by(Book.title).all()
    return render_template('books.html', theme=get_theme(), books=all_books)


# ── Pamphlets ─────────────────────────────────────────────────────────────────

@main_bp.route('/pamphlets')
def pamphlets():
    from ..models import Pamphlet
    all_pamphlets = Pamphlet.query.order_by(Pamphlet.title).all()
    return render_template('pamphlets.html', theme=get_theme(), pamphlets=all_pamphlets)


# ── Dictionary ────────────────────────────────────────────────────────────────

@main_bp.route('/dictionary')
def dictionary():
    from ..models import Dictionary
    entries = Dictionary.query.order_by(Dictionary.word_phrase).all()
    return render_template('dictionary.html', theme=get_theme(), entries=entries)


# ── Book content ──────────────────────────────────────────────────────────────

@main_bp.route('/book-content')
def book_content():
    books = Book.query.order_by(Book.title).all()
    book_id = request.args.get('book_id', type=int)
    page_filter = request.args.get('page', '')
    content = []
    selected_book = None
    if book_id:
        selected_book = Book.query.get(book_id)
        q = BookContent.query.filter_by(book_id=book_id)
        if page_filter:
            q = q.filter_by(page=page_filter)
        content = q.order_by(BookContent.chapter, BookContent.page,
                             BookContent.paragraph, BookContent.line).all()
    return render_template('book_content.html', theme=get_theme(),
                           books=books, content=content,
                           selected_book=selected_book, page_filter=page_filter)


# ── References ────────────────────────────────────────────────────────────────

@main_bp.route('/references')
def references():
    from ..models import BookReference
    refs = BookReference.query.order_by(BookReference.created_at.desc()).all()
    books = Book.query.order_by(Book.title).all()
    return render_template('references.html', theme=get_theme(), refs=refs, books=books)


# ── Commentary ────────────────────────────────────────────────────────────────

@main_bp.route('/commentary')
def commentary():
    from ..models import Commentary
    entries = Commentary.query.order_by(Commentary.created_at.desc()).all()
    books = Book.query.order_by(Book.title).all()
    return render_template('commentary.html', theme=get_theme(), entries=entries, books=books)


# ── Sources ───────────────────────────────────────────────────────────────────

@main_bp.route('/sources')
def sources():
    from ..models import Source
    all_sources = Source.query.order_by(Source.name).all()
    return render_template('sources.html', theme=get_theme(), sources=all_sources)

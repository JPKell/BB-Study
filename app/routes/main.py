import os
from flask import Blueprint, abort, current_app, render_template, request, redirect, send_from_directory, url_for
from ..models import Setting, Book, BookContent, BookTableOfContents
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


def get_current_content_mode():
    s = Setting.query.filter_by(key='current_content_mode').first()
    value = s.value if s else 'sentence'
    return value if value in ('sentence', 'line') else 'sentence'


def _set_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    value = '' if value is None else str(value)
    if setting:
        if setting.value != value:
            setting.value = value
            db.session.commit()
        return
    db.session.add(Setting(key=key, value=value))
    db.session.commit()


# ── Reading page ──────────────────────────────────────────────────────────────

@main_bp.route('/')
def index():
    theme = get_theme()
    book_id = request.args.get('book_id', type=int)
    current_book = Book.query.get(book_id) if book_id else get_current_book()
    current_page = request.args.get('page') or get_current_page()
    content_mode = request.args.get('content_mode') or get_current_content_mode()
    if content_mode not in ('sentence', 'line'):
        content_mode = 'sentence'
    books = Book.query.order_by(Book.title).all()

    page_content = []
    toc_entries = []
    previous_page = None
    next_page = None
    if current_book:
        # Keep reading position sticky across navigation to/from other pages.
        if book_id:
            _set_setting('current_book_id', current_book.id)
        if request.args.get('page'):
            _set_setting('current_page', current_page)
        if request.args.get('content_mode'):
            _set_setting('current_content_mode', content_mode)

        page_rows = (db.session.query(BookContent.page)
                     .filter_by(book_id=current_book.id)
                     .distinct()
                     .all())
        page_values = [row[0] for row in page_rows if row[0]]
        page_values.sort(key=_page_sort_key)
        if current_page in page_values:
            index = page_values.index(current_page)
            if index > 0:
                previous_page = page_values[index - 1]
            if index < len(page_values) - 1:
                next_page = page_values[index + 1]
        q = BookContent.query.filter_by(book_id=current_book.id, page=current_page)
        if content_mode == 'sentence':
            q = q.order_by(BookContent.paragraph, BookContent.verse, BookContent.line, BookContent.id)
        else:
            q = q.order_by(BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id)
        page_content = q.all()
        toc_entries = (BookTableOfContents.query
                       .filter_by(book_id=current_book.id)
                       .order_by(BookTableOfContents.sort_order, BookTableOfContents.id)
                       .all())

    return render_template('index.html',
                           theme=theme,
                           current_book=current_book,
                           current_page=current_page,
                           previous_page=previous_page,
                           next_page=next_page,
                           content_mode=content_mode,
                           page_content=page_content,
                           toc_entries=toc_entries,
                           books=books)


def _page_sort_key(page):
    page = str(page)
    if page.startswith('front-'):
        return (0, page)
    roman_values = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
    if page.isdigit():
        return (2, int(page))
    total = 0
    previous = 0
    for char in reversed(page.lower()):
        value = roman_values.get(char, 0)
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return (1, total or page)


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
    pg = request.args.get('pg', 1, type=int)
    pagination = Book.query.order_by(Book.title).paginate(page=pg, per_page=25, error_out=False)
    return render_template('books.html', theme=get_theme(), books=pagination.items, pagination=pagination)


# ── Pamphlets ─────────────────────────────────────────────────────────────────

@main_bp.route('/pamphlets')
def pamphlets():
    from ..models import Pamphlet
    pg = request.args.get('pg', 1, type=int)
    pagination = Pamphlet.query.order_by(Pamphlet.series).paginate(page=pg, per_page=25, error_out=False)
    return render_template('pamphlets.html', theme=get_theme(), pamphlets=pagination.items, pagination=pagination)


# ── Dictionary ────────────────────────────────────────────────────────────────

@main_bp.route('/dictionary')
def dictionary():
    from ..models import Dictionary
    pg = request.args.get('pg', 1, type=int)
    search_q = request.args.get('q', '').strip()
    query = Dictionary.query.order_by(Dictionary.word_phrase)
    if search_q:
        like = f'%{search_q}%'
        query = query.filter(
            Dictionary.word_phrase.ilike(like) | Dictionary.meaning.ilike(like)
        )
    pagination = query.paginate(page=pg, per_page=30, error_out=False)
    return render_template('dictionary.html', theme=get_theme(), entries=pagination.items,
                           pagination=pagination, search_q=search_q)


# ── Topics ───────────────────────────────────────────────────────────────────

@main_bp.route('/topics')
def topics():
    from ..models import Topic
    pg = request.args.get('pg', 1, type=int)
    pagination = Topic.query.order_by(Topic.name).paginate(page=pg, per_page=25, error_out=False)
    books = Book.query.order_by(Book.title).all()
    return render_template('topics.html', theme=get_theme(), topics=pagination.items,
                           pagination=pagination, books=books)


@main_bp.route('/search')
def search():
    books = Book.query.order_by(Book.title).all()
    return render_template('search.html', theme=get_theme(), books=books)


# ── Book content ──────────────────────────────────────────────────────────────

@main_bp.route('/book-content')
def book_content():
    books = Book.query.order_by(Book.title).all()
    book_id = request.args.get('book_id', type=int)
    page_filter = request.args.get('page', '')
    content_mode = request.args.get('content_mode', 'sentence')
    if content_mode not in ('sentence', 'line'):
        content_mode = 'sentence'
    pg = request.args.get('pg', 1, type=int)
    content = []
    toc_entries = []
    selected_book = None
    pagination = None
    if book_id:
        selected_book = Book.query.get(book_id)
        toc_entries = (BookTableOfContents.query
                       .filter_by(book_id=book_id)
                       .order_by(BookTableOfContents.sort_order, BookTableOfContents.id)
                       .all())
        q = BookContent.query.filter_by(book_id=book_id)
        if page_filter:
            q = q.filter_by(page=page_filter)
        q = q.order_by(BookContent.chapter_number, BookContent.chapter_name, BookContent.page,
                       BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id)
        pagination = q.paginate(page=pg, per_page=50, error_out=False)
        content = pagination.items
    return render_template('book_content.html', theme=get_theme(),
                           books=books, content=content,
                           selected_book=selected_book, page_filter=page_filter,
                           toc_entries=toc_entries, content_mode=content_mode,
                           pagination=pagination)


@main_bp.route('/books/<int:book_id>/pdf')
def book_pdf(book_id):
    book = Book.query.get_or_404(book_id)
    if not book.pdf_path:
        abort(404)

    pdf_root = os.path.abspath(os.path.join(current_app.root_path, 'pdf'))
    pdf_path = os.path.abspath(os.path.join(pdf_root, book.pdf_path))
    if not pdf_path.startswith(pdf_root + os.sep) or not os.path.isfile(pdf_path):
        abort(404)

    rel_dir = os.path.relpath(os.path.dirname(pdf_path), pdf_root)
    return send_from_directory(os.path.join(pdf_root, rel_dir), os.path.basename(pdf_path))


# ── References ────────────────────────────────────────────────────────────────

@main_bp.route('/references')
def references():
    from ..models import BookReference
    pg = request.args.get('pg', 1, type=int)
    pagination = BookReference.query.order_by(BookReference.created_at.desc()).paginate(
        page=pg, per_page=25, error_out=False)
    books = Book.query.order_by(Book.title).all()
    return render_template('references.html', theme=get_theme(), refs=pagination.items,
                           pagination=pagination, books=books)


# ── Commentary ────────────────────────────────────────────────────────────────

@main_bp.route('/commentary')
def commentary():
    from ..models import Commentary
    pg = request.args.get('pg', 1, type=int)
    pagination = Commentary.query.order_by(Commentary.created_at.desc()).paginate(
        page=pg, per_page=25, error_out=False)
    books = Book.query.order_by(Book.title).all()
    return render_template('commentary.html', theme=get_theme(), entries=pagination.items,
                           pagination=pagination, books=books)


# ── Sources ───────────────────────────────────────────────────────────────────

@main_bp.route('/sources')
def sources():
    from ..models import Source
    all_sources = Source.query.order_by(Source.name).all()
    return render_template('sources.html', theme=get_theme(), sources=all_sources)

import os
from flask import Blueprint, abort, current_app, render_template, request, redirect, send_file, send_from_directory, url_for
from ..models import Setting, Book, BookContent, BookContentFormat, BookTableOfContents
from .. import db

main_bp = Blueprint('main', __name__)
EXPORT_TEXT_LAYOUTS = {'reflow_justified'}
EXPORT_ALIGNMENTS = {'left', 'justify', 'center'}
EXPORT_FONT_OPTIONS = {'Times-Roman', 'Helvetica', 'Courier'}
EXPORT_PAGE_SIZES = {'letter', 'half_letter'}
EXPORT_SETTING_DEFAULTS = {
    'export_text_layout': 'reflow_justified',
    'export_page_size': 'letter',
    'export_book_alignment': 'justify',
    'export_definition_alignment': 'left',
    'export_commentary_alignment': 'left',
    'export_margin_top': '0.45',
    'export_margin_bottom': '0.45',
    'export_chapter_gap': '0.46',
    'export_page_number_gap': '0.35',
    'export_inside_margin': '0.80',
    'export_outside_margin': '0.45',
    'export_column_gutter': '0.22',
    'export_text_ratio': '0.667',
    'export_commentary_columns': '3',
    'export_commentary_column_gutter': '0.32',
    'export_one_column_top': '0',
    'export_section_gap': '0.18',
    'export_rule_margin_above': '0.04',
    'export_rule_margin_below': '0.21',
    'export_chapter_font_size': '8.5',
    'export_page_number_font_size': '8',
    'export_book_font_size': '10.2',
    'export_definition_font_size': '8.3',
    'export_commentary_font_size': '7',
    'export_annotation_font_size': '9',
    'export_chapter_line_spacing': '1.0',
    'export_page_number_line_spacing': '1.0',
    'export_book_line_spacing': '1.35',
    'export_definition_line_spacing': '1.3',
    'export_commentary_line_spacing': '1.28',
    'export_annotation_line_spacing': '1.33',
    'export_chapter_kerning': '0',
    'export_page_number_kerning': '0',
    'export_book_kerning': '0',
    'export_definition_kerning': '0',
    'export_commentary_kerning': '0',
    'export_annotation_kerning': '0',
    'export_chapter_font': 'Helvetica',
    'export_page_number_font': 'Helvetica',
    'export_book_font': 'Times-Roman',
    'export_definition_font': 'Helvetica',
    'export_commentary_font': 'Helvetica',
    'export_annotation_font': 'Helvetica',
    'export_chapter_gray': '30',
    'export_page_number_gray': '40',
    'export_book_gray': '0',
    'export_definition_gray': '0',
    'export_commentary_gray': '0',
    'export_annotation_gray': '0',
}


def get_theme():
    s = Setting.query.filter_by(key='theme').first()
    return s.value if s else 'dark'


def get_current_book():
    s = Setting.query.filter_by(key='current_book_id').first()
    if s and s.value:
        return Book.query.get(int(s.value))
    return None


def get_current_secondary_book():
    s = Setting.query.filter_by(key='current_secondary_book_id').first()
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


def _get_setting(key, default=''):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting and setting.value != '' else default


def get_export_text_layout():
    value = _get_setting('export_text_layout', 'reflow_justified')
    return value if value in EXPORT_TEXT_LAYOUTS else 'reflow_justified'


def get_export_setting_values():
    values = {}
    for key, default in EXPORT_SETTING_DEFAULTS.items():
        values[key] = _get_setting(key, default)
    values['export_text_layout'] = (
        values['export_text_layout']
        if values['export_text_layout'] in EXPORT_TEXT_LAYOUTS
        else 'reflow_justified'
    )
    for key in ('export_book_alignment', 'export_definition_alignment', 'export_commentary_alignment'):
        if values.get(key) not in EXPORT_ALIGNMENTS:
            values[key] = EXPORT_SETTING_DEFAULTS[key]
    if values.get('export_page_size') not in EXPORT_PAGE_SIZES:
        values['export_page_size'] = EXPORT_SETTING_DEFAULTS['export_page_size']
    return values


def _export_float_setting(values, key, minimum=None, maximum=None):
    default = float(EXPORT_SETTING_DEFAULTS[key])
    try:
        value = float(values.get(key, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _export_int_setting(values, key, minimum=None, maximum=None):
    default = int(float(EXPORT_SETTING_DEFAULTS[key]))
    try:
        value = int(float(values.get(key, default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _export_bool_setting(values, key):
    return str(values.get(key, EXPORT_SETTING_DEFAULTS[key])).lower() in ('1', 'true', 'yes', 'on')


def _export_font_setting(values, key):
    value = values.get(key, EXPORT_SETTING_DEFAULTS[key])
    return value if value in EXPORT_FONT_OPTIONS else EXPORT_SETTING_DEFAULTS[key]


def build_export_layout():
    from reportlab.lib.units import inch
    from reportlab.lib.pagesizes import letter
    from ..services.page_pdf_exporter import ExportLayout

    values = get_export_setting_values()
    page_size = (5.5 * inch, 8.5 * inch) if values['export_page_size'] == 'half_letter' else letter
    return ExportLayout(
        page_size=page_size,
        text_layout=values['export_text_layout'],
        book_alignment=values['export_book_alignment'],
        definition_alignment=values['export_definition_alignment'],
        commentary_alignment=values['export_commentary_alignment'],
        top_margin=_export_float_setting(values, 'export_margin_top', 0.1, 2.0) * inch,
        bottom_margin=_export_float_setting(values, 'export_margin_bottom', 0.1, 2.0) * inch,
        header_gap=_export_float_setting(values, 'export_chapter_gap', 0.1, 2.0) * inch,
        page_number_gap=_export_float_setting(values, 'export_page_number_gap', 0.1, 1.5) * inch,
        inside_margin=_export_float_setting(values, 'export_inside_margin', 0.1, 2.0) * inch,
        outside_margin=_export_float_setting(values, 'export_outside_margin', 0.1, 2.0) * inch,
        column_gutter=_export_float_setting(values, 'export_column_gutter', 0.05, 1.0) * inch,
        text_ratio=_export_float_setting(values, 'export_text_ratio', 0.45, 0.85),
        commentary_columns=_export_int_setting(values, 'export_commentary_columns', 1, 4),
        commentary_column_gutter=_export_float_setting(values, 'export_commentary_column_gutter', 0.05, 1.0) * inch,
        one_column_top=_export_bool_setting(values, 'export_one_column_top'),
        section_gap=_export_float_setting(values, 'export_section_gap', 0, 1.0) * inch,
        rule_margin_above=_export_float_setting(values, 'export_rule_margin_above', 0, 0.75) * inch,
        rule_margin_below=_export_float_setting(values, 'export_rule_margin_below', 0, 0.75) * inch,
        chapter_font_size=_export_float_setting(values, 'export_chapter_font_size', 6, 18),
        page_number_font_size=_export_float_setting(values, 'export_page_number_font_size', 6, 18),
        book_font_size=_export_float_setting(values, 'export_book_font_size', 6, 18),
        definition_font_size=_export_float_setting(values, 'export_definition_font_size', 5, 16),
        commentary_font_size=_export_float_setting(values, 'export_commentary_font_size', 5, 16),
        annotation_font_size=_export_float_setting(values, 'export_annotation_font_size', 5, 16),
        chapter_line_spacing=_export_float_setting(values, 'export_chapter_line_spacing', 0.8, 2.0),
        page_number_line_spacing=_export_float_setting(values, 'export_page_number_line_spacing', 0.8, 2.0),
        book_line_spacing=_export_float_setting(values, 'export_book_line_spacing', 0.8, 2.0),
        definition_line_spacing=_export_float_setting(values, 'export_definition_line_spacing', 0.8, 2.0),
        commentary_line_spacing=_export_float_setting(values, 'export_commentary_line_spacing', 0.8, 2.0),
        annotation_line_spacing=_export_float_setting(values, 'export_annotation_line_spacing', 0.8, 2.0),
        chapter_kerning=_export_float_setting(values, 'export_chapter_kerning', -1.0, 2.0),
        page_number_kerning=_export_float_setting(values, 'export_page_number_kerning', -1.0, 2.0),
        book_kerning=_export_float_setting(values, 'export_book_kerning', -1.0, 2.0),
        definition_kerning=_export_float_setting(values, 'export_definition_kerning', -1.0, 2.0),
        commentary_kerning=_export_float_setting(values, 'export_commentary_kerning', -1.0, 2.0),
        annotation_kerning=_export_float_setting(values, 'export_annotation_kerning', -1.0, 2.0),
        chapter_font=_export_font_setting(values, 'export_chapter_font'),
        page_number_font=_export_font_setting(values, 'export_page_number_font'),
        book_font=_export_font_setting(values, 'export_book_font'),
        definition_font=_export_font_setting(values, 'export_definition_font'),
        commentary_font=_export_font_setting(values, 'export_commentary_font'),
        annotation_font=_export_font_setting(values, 'export_annotation_font'),
        chapter_gray=_export_float_setting(values, 'export_chapter_gray', 0, 90),
        page_number_gray=_export_float_setting(values, 'export_page_number_gray', 0, 90),
        book_gray=_export_float_setting(values, 'export_book_gray', 0, 90),
        definition_gray=_export_float_setting(values, 'export_definition_gray', 0, 90),
        commentary_gray=_export_float_setting(values, 'export_commentary_gray', 0, 90),
        annotation_gray=_export_float_setting(values, 'export_annotation_gray', 0, 90),
    )


def _book_position_key(book_id, suffix):
    return f'book_{book_id}_{suffix}'


def get_book_page(book_id, default='1'):
    if not book_id:
        return default
    return _get_setting(_book_position_key(book_id, 'page'), default)


def get_book_content_mode(book_id, default='sentence'):
    if not book_id:
        return default
    value = _get_setting(_book_position_key(book_id, 'content_mode'), default)
    return value if value in ('sentence', 'line') else 'sentence'


def get_facing_page(book_id, page):
    try:
        page_number = int(str(page))
    except (TypeError, ValueError):
        return None
    facing_page = page_number - 1 if page_number % 2 else page_number + 1
    if facing_page < 1:
        return None
    facing_page = str(facing_page)
    exists = BookContent.query.filter_by(book_id=book_id, page=facing_page).first()
    return facing_page if exists else None


def get_preview_page_numbers(book, page):
    if not book:
        return []
    facing_page = get_facing_page(book.id, page)
    pages = [str(page)]
    if facing_page:
        pages.append(facing_page)
    pages.sort(key=_page_sort_key)
    return pages


def build_preview_pages(book, page):
    pages = get_preview_page_numbers(book, page)
    return [
        {
            'page': preview_page,
            'url': url_for('main.export_page_pdf', book_id=book.id, page=preview_page),
        }
        for preview_page in pages
    ]


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


def _build_reader_state(book, page, content_mode):
    state = {
        'book': book,
        'page': page,
        'content_mode': content_mode,
        'page_content': [],
        'content_formats': {},
        'toc_entries': [],
        'previous_page': None,
        'next_page': None,
    }
    if not book:
        return state

    page_rows = (db.session.query(BookContent.page)
                 .filter_by(book_id=book.id)
                 .distinct()
                 .all())
    page_values = [row[0] for row in page_rows if row[0]]
    page_values.sort(key=_page_sort_key)
    if page in page_values:
        index = page_values.index(page)
        if index > 0:
            state['previous_page'] = page_values[index - 1]
        if index < len(page_values) - 1:
            state['next_page'] = page_values[index + 1]

    q = BookContent.query.filter_by(book_id=book.id, page=page)
    if content_mode == 'sentence':
        q = q.order_by(BookContent.paragraph, BookContent.verse, BookContent.line, BookContent.id)
    else:
        q = q.order_by(BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id)
    state['page_content'] = q.all()
    formats = (BookContentFormat.query
               .filter_by(book_id=book.id, page=page)
               .all())
    state['content_formats'] = {
        f'{fmt.paragraph}-{fmt.verse}': fmt
        for fmt in formats
        if fmt.paragraph is not None and fmt.verse is not None
    }
    state['toc_entries'] = (BookTableOfContents.query
                            .filter_by(book_id=book.id)
                            .order_by(BookTableOfContents.sort_order, BookTableOfContents.id)
                            .all())
    return state


# ── Reading page ──────────────────────────────────────────────────────────────

@main_bp.route('/')
def index():
    theme = get_theme()
    book_id = request.args.get('book_id', type=int)
    current_book = Book.query.get(book_id) if book_id else get_current_book()
    current_page = request.args.get('page') or (
        get_book_page(current_book.id, get_current_page()) if current_book else get_current_page()
    )
    content_mode = request.args.get('content_mode') or (
        get_book_content_mode(current_book.id, get_current_content_mode()) if current_book else get_current_content_mode()
    )
    if content_mode not in ('sentence', 'line'):
        content_mode = 'sentence'

    secondary_book_id = request.args.get('secondary_book_id', type=int)
    secondary_book = Book.query.get(secondary_book_id) if secondary_book_id else get_current_secondary_book()
    secondary_page = request.args.get('secondary_page') or (
        get_book_page(secondary_book.id, '1') if secondary_book else '1'
    )
    secondary_content_mode = request.args.get('secondary_content_mode') or (
        get_book_content_mode(secondary_book.id, 'sentence') if secondary_book else 'sentence'
    )
    if secondary_content_mode not in ('sentence', 'line'):
        secondary_content_mode = 'sentence'

    books = Book.query.order_by(Book.title).all()

    if current_book:
        # Keep reading position sticky across navigation to/from other pages.
        if book_id:
            _set_setting('current_book_id', current_book.id)
        if request.args.get('page'):
            _set_setting('current_page', current_page)
            _set_setting(_book_position_key(current_book.id, 'page'), current_page)
        if request.args.get('content_mode'):
            _set_setting('current_content_mode', content_mode)
            _set_setting(_book_position_key(current_book.id, 'content_mode'), content_mode)

    if secondary_book:
        if secondary_book_id:
            _set_setting('current_secondary_book_id', secondary_book.id)
        if request.args.get('secondary_page'):
            _set_setting(_book_position_key(secondary_book.id, 'page'), secondary_page)
        if request.args.get('secondary_content_mode'):
            _set_setting(_book_position_key(secondary_book.id, 'content_mode'), secondary_content_mode)

    primary_state = _build_reader_state(current_book, current_page, content_mode)
    secondary_state = _build_reader_state(secondary_book, secondary_page, secondary_content_mode)

    return render_template('index.html',
                           theme=theme,
                           current_book=current_book,
                           current_page=current_page,
                           previous_page=primary_state['previous_page'],
                           next_page=primary_state['next_page'],
                           content_mode=content_mode,
                           page_content=primary_state['page_content'],
                           content_formats=primary_state['content_formats'],
                           toc_entries=primary_state['toc_entries'],
                           secondary_book=secondary_book,
                           secondary_page=secondary_page,
                           secondary_previous_page=secondary_state['previous_page'],
                           secondary_next_page=secondary_state['next_page'],
                           secondary_content_mode=secondary_content_mode,
                           secondary_page_content=secondary_state['page_content'],
                           secondary_content_formats=secondary_state['content_formats'],
                           secondary_toc_entries=secondary_state['toc_entries'],
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
    export_settings = get_export_setting_values()
    preview_book = get_current_book()
    preview_page = (
        get_book_page(preview_book.id, get_current_page()) if preview_book else get_current_page()
    )
    preview_pages = build_preview_pages(preview_book, preview_page)
    preview_pdf_url = (
        url_for('main.export_page_spread_pdf', book_id=preview_book.id, page=preview_page)
        if preview_pages else None
    )
    if request.method == 'POST':
        new_theme = request.form.get('theme', 'dark')
        s = Setting.query.filter_by(key='theme').first()
        if s:
            s.value = new_theme
        else:
            db.session.add(Setting(key='theme', value=new_theme))
        db.session.commit()
        return redirect(url_for('main.settings'))
    return render_template('settings.html', theme=theme,
                           export_settings=export_settings,
                           export_text_layout=export_settings['export_text_layout'],
                           preview_book=preview_book,
                           preview_page=preview_page,
                           preview_pdf_url=preview_pdf_url,
                           preview_pages=preview_pages)


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


@main_bp.route('/books/<int:book_id>/pages/<page>/export.pdf')
def export_page_pdf(book_id, page):
    from ..services.page_pdf_exporter import export_page_pdf as build_page_pdf
    book = Book.query.get_or_404(book_id)
    layout = build_export_layout()
    pdf_buffer = build_page_pdf(book_id, page, layout=layout)
    filename = f'{book.title}-page-{page}.pdf'.replace('/', '-')
    response = send_file(pdf_buffer, mimetype='application/pdf',
                         as_attachment=False, download_name=filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@main_bp.route('/books/<int:book_id>/pages/<page>/export-spread.pdf')
def export_page_spread_pdf(book_id, page):
    from ..services.page_pdf_exporter import export_pages_pdf as build_pages_pdf
    book = Book.query.get_or_404(book_id)
    pages = get_preview_page_numbers(book, page) or [str(page)]
    layout = build_export_layout()
    pdf_buffer = build_pages_pdf(book_id, pages, layout=layout)
    page_label = '-'.join(pages)
    filename = f'{book.title}-pages-{page_label}.pdf'.replace('/', '-')
    response = send_file(pdf_buffer, mimetype='application/pdf',
                         as_attachment=False, download_name=filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


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

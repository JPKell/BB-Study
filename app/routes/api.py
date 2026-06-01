"""
REST API – all responses are JSON.
Convention: POST = create, PUT = update, DELETE = delete.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from ..models import (Setting, Book, Pamphlet, Dictionary, BookLocation,
                      DictionaryLookup, BookReference, BookContent,
                      Commentary, Source)
from .. import db

api_bp = Blueprint('api', __name__)


def _err(msg, code=400):
    return jsonify({'error': msg}), code


def _ok(data=None, msg='OK'):
    return jsonify({'status': 'ok', 'message': msg, 'data': data})


# ── Settings ──────────────────────────────────────────────────────────────────

@api_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({s.key: s.value for s in Setting.query.all()})


@api_bp.route('/settings/<key>', methods=['PUT'])
def update_setting(key):
    data = request.get_json(force=True) or {}
    s = Setting.query.filter_by(key=key).first()
    if not s:
        s = Setting(key=key)
        db.session.add(s)
    s.value = data.get('value', '')
    db.session.commit()
    return _ok(s.to_dict())


# ── Books ─────────────────────────────────────────────────────────────────────

@api_bp.route('/books', methods=['GET'])
def list_books():
    return jsonify([b.to_dict() for b in Book.query.order_by(Book.title).all()])


@api_bp.route('/books', methods=['POST'])
def create_book():
    data = request.get_json(force=True) or {}
    if not data.get('title'):
        return _err('title is required')
    # If is_primary is being set, clear other primary books
    if data.get('is_primary'):
        Book.query.filter_by(is_primary=True).update({'is_primary': False})
    book = Book(
        title=data['title'],
        author=data.get('author'),
        isbn=data.get('isbn'),
        publisher=data.get('publisher'),
        publish_date=data.get('publish_date'),
        edition=data.get('edition'),
        notes=data.get('notes'),
        is_primary=bool(data.get('is_primary', False)),
    )
    db.session.add(book)
    db.session.commit()
    return _ok(book.to_dict(), 'Book created'), 201


@api_bp.route('/books/<int:book_id>', methods=['GET'])
def get_book(book_id):
    book = Book.query.get_or_404(book_id)
    return jsonify(book.to_dict())


@api_bp.route('/books/<int:book_id>', methods=['PUT'])
def update_book(book_id):
    book = Book.query.get_or_404(book_id)
    data = request.get_json(force=True) or {}
    if data.get('is_primary') and not book.is_primary:
        Book.query.filter_by(is_primary=True).update({'is_primary': False})
    for field in ('title', 'author', 'isbn', 'publisher', 'publish_date', 'edition', 'notes'):
        if field in data:
            setattr(book, field, data[field])
    if 'is_primary' in data:
        book.is_primary = bool(data['is_primary'])
    db.session.commit()
    return _ok(book.to_dict())


@api_bp.route('/books/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    db.session.delete(book)
    db.session.commit()
    return _ok(msg='Book deleted')


# ── Pamphlets ─────────────────────────────────────────────────────────────────

@api_bp.route('/pamphlets', methods=['GET'])
def list_pamphlets():
    return jsonify([p.to_dict() for p in Pamphlet.query.order_by(Pamphlet.title).all()])


@api_bp.route('/pamphlets', methods=['POST'])
def create_pamphlet():
    data = request.get_json(force=True) or {}
    if not data.get('title'):
        return _err('title is required')
    p = Pamphlet(
        title=data['title'],
        author=data.get('author'),
        publisher=data.get('publisher'),
        publish_date=data.get('publish_date'),
        series=data.get('series'),
        notes=data.get('notes'),
    )
    db.session.add(p)
    db.session.commit()
    return _ok(p.to_dict(), 'Pamphlet created'), 201


@api_bp.route('/pamphlets/<int:pid>', methods=['GET'])
def get_pamphlet(pid):
    return jsonify(Pamphlet.query.get_or_404(pid).to_dict())


@api_bp.route('/pamphlets/<int:pid>', methods=['PUT'])
def update_pamphlet(pid):
    p = Pamphlet.query.get_or_404(pid)
    data = request.get_json(force=True) or {}
    for field in ('title', 'author', 'publisher', 'publish_date', 'series', 'notes'):
        if field in data:
            setattr(p, field, data[field])
    db.session.commit()
    return _ok(p.to_dict())


@api_bp.route('/pamphlets/<int:pid>', methods=['DELETE'])
def delete_pamphlet(pid):
    p = Pamphlet.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return _ok(msg='Pamphlet deleted')


# ── Dictionary ────────────────────────────────────────────────────────────────

@api_bp.route('/dictionary', methods=['GET'])
def list_dictionary():
    q = request.args.get('q', '').strip()
    query = Dictionary.query
    if q:
        query = query.filter(Dictionary.word_phrase.ilike(f'%{q}%'))
    return jsonify([e.to_dict() for e in query.order_by(Dictionary.word_phrase).all()])


@api_bp.route('/dictionary', methods=['POST'])
def create_dictionary():
    data = request.get_json(force=True) or {}
    if not data.get('word_phrase') or not data.get('meaning'):
        return _err('word_phrase and meaning are required')
    entry = Dictionary(
        word_phrase=data['word_phrase'],
        meaning=data['meaning'],
        notes=data.get('notes'),
    )
    db.session.add(entry)
    db.session.commit()
    return _ok(entry.to_dict(), 'Entry created'), 201


@api_bp.route('/dictionary/<int:eid>', methods=['GET'])
def get_dictionary(eid):
    return jsonify(Dictionary.query.get_or_404(eid).to_dict())


@api_bp.route('/dictionary/<int:eid>', methods=['PUT'])
def update_dictionary(eid):
    entry = Dictionary.query.get_or_404(eid)
    data = request.get_json(force=True) or {}
    for field in ('word_phrase', 'meaning', 'notes'):
        if field in data:
            setattr(entry, field, data[field])
    db.session.commit()
    return _ok(entry.to_dict())


@api_bp.route('/dictionary/<int:eid>', methods=['DELETE'])
def delete_dictionary(eid):
    entry = Dictionary.query.get_or_404(eid)
    db.session.delete(entry)
    db.session.commit()
    return _ok(msg='Entry deleted')


# ── Book Locations ────────────────────────────────────────────────────────────

@api_bp.route('/book-locations', methods=['GET'])
def list_book_locations():
    book_id = request.args.get('book_id', type=int)
    q = BookLocation.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    return jsonify([loc.to_dict() for loc in q.all()])


@api_bp.route('/book-locations', methods=['POST'])
def create_book_location():
    data = request.get_json(force=True) or {}
    if not data.get('book_id'):
        return _err('book_id is required')
    loc = BookLocation(
        book_id=data['book_id'],
        chapter=data.get('chapter'),
        page=data.get('page'),
        paragraph=data.get('paragraph'),
        line_number=data.get('line_number'),
        line_text=data.get('line_text'),
    )
    db.session.add(loc)
    db.session.commit()
    return _ok(loc.to_dict(), 'Location created'), 201


@api_bp.route('/book-locations/<int:lid>', methods=['PUT'])
def update_book_location(lid):
    loc = BookLocation.query.get_or_404(lid)
    data = request.get_json(force=True) or {}
    for field in ('book_id', 'chapter', 'page', 'paragraph', 'line_number', 'line_text'):
        if field in data:
            setattr(loc, field, data[field])
    db.session.commit()
    return _ok(loc.to_dict())


@api_bp.route('/book-locations/<int:lid>', methods=['DELETE'])
def delete_book_location(lid):
    loc = BookLocation.query.get_or_404(lid)
    db.session.delete(loc)
    db.session.commit()
    return _ok(msg='Location deleted')


# ── Dictionary Lookup ─────────────────────────────────────────────────────────

@api_bp.route('/dictionary-lookup', methods=['GET'])
def list_dictionary_lookup():
    dict_id = request.args.get('dictionary_id', type=int)
    loc_id = request.args.get('book_location_id', type=int)
    q = DictionaryLookup.query
    if dict_id:
        q = q.filter_by(dictionary_id=dict_id)
    if loc_id:
        q = q.filter_by(book_location_id=loc_id)
    return jsonify([lk.to_dict() for lk in q.all()])


@api_bp.route('/dictionary-lookup', methods=['POST'])
def create_dictionary_lookup():
    data = request.get_json(force=True) or {}
    if not data.get('dictionary_id') or not data.get('book_location_id'):
        return _err('dictionary_id and book_location_id are required')
    lk = DictionaryLookup(
        dictionary_id=data['dictionary_id'],
        book_location_id=data['book_location_id'],
    )
    db.session.add(lk)
    db.session.commit()
    return _ok(lk.to_dict(), 'Lookup created'), 201


@api_bp.route('/dictionary-lookup/<int:lid>', methods=['DELETE'])
def delete_dictionary_lookup(lid):
    lk = DictionaryLookup.query.get_or_404(lid)
    db.session.delete(lk)
    db.session.commit()
    return _ok(msg='Lookup deleted')


# ── Book References ───────────────────────────────────────────────────────────

@api_bp.route('/references', methods=['GET'])
def list_references():
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page')
    q = BookReference.query
    if book_id:
        q = q.filter(
            (BookReference.source_book_id == book_id) |
            (BookReference.target_book_id == book_id)
        )
    if page:
        q = q.filter(
            (BookReference.source_page == page) |
            (BookReference.target_page == page)
        )
    return jsonify([r.to_dict() for r in q.order_by(BookReference.created_at.desc()).all()])


@api_bp.route('/references', methods=['POST'])
def create_reference():
    data = request.get_json(force=True) or {}
    if not data.get('source_book_id') or not data.get('target_book_id'):
        return _err('source_book_id and target_book_id are required')
    ref = BookReference(
        source_book_id=data['source_book_id'],
        source_chapter=data.get('source_chapter'),
        source_page=data.get('source_page'),
        source_paragraph=data.get('source_paragraph'),
        source_line=data.get('source_line'),
        target_book_id=data['target_book_id'],
        target_chapter=data.get('target_chapter'),
        target_page=data.get('target_page'),
        target_paragraph=data.get('target_paragraph'),
        target_line=data.get('target_line'),
        quoted_text=data.get('quoted_text'),
        comments=data.get('comments'),
    )
    db.session.add(ref)
    db.session.commit()
    return _ok(ref.to_dict(), 'Reference created'), 201


@api_bp.route('/references/<int:rid>', methods=['GET'])
def get_reference(rid):
    return jsonify(BookReference.query.get_or_404(rid).to_dict())


@api_bp.route('/references/<int:rid>', methods=['PUT'])
def update_reference(rid):
    ref = BookReference.query.get_or_404(rid)
    data = request.get_json(force=True) or {}
    fields = ('source_book_id', 'source_chapter', 'source_page', 'source_paragraph',
              'source_line', 'target_book_id', 'target_chapter', 'target_page',
              'target_paragraph', 'target_line', 'quoted_text', 'comments')
    for field in fields:
        if field in data:
            setattr(ref, field, data[field])
    db.session.commit()
    return _ok(ref.to_dict())


@api_bp.route('/references/<int:rid>', methods=['DELETE'])
def delete_reference(rid):
    ref = BookReference.query.get_or_404(rid)
    db.session.delete(ref)
    db.session.commit()
    return _ok(msg='Reference deleted')


# ── Book Content ──────────────────────────────────────────────────────────────

@api_bp.route('/book-content', methods=['GET'])
def list_book_content():
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page')
    chapter = request.args.get('chapter')
    q = BookContent.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    if page:
        q = q.filter_by(page=page)
    if chapter:
        q = q.filter_by(chapter=chapter)
    results = q.order_by(BookContent.chapter, BookContent.page,
                         BookContent.paragraph, BookContent.line).all()
    return jsonify([r.to_dict() for r in results])


@api_bp.route('/book-content', methods=['POST'])
def create_book_content():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('content'):
        return _err('book_id and content are required')
    bc = BookContent(
        book_id=data['book_id'],
        chapter=data.get('chapter'),
        page=data.get('page'),
        paragraph=data.get('paragraph'),
        line=data.get('line'),
        content=data['content'],
    )
    db.session.add(bc)
    db.session.commit()
    return _ok(bc.to_dict(), 'Content created'), 201


@api_bp.route('/book-content/<int:cid>', methods=['GET'])
def get_book_content(cid):
    return jsonify(BookContent.query.get_or_404(cid).to_dict())


@api_bp.route('/book-content/<int:cid>', methods=['PUT'])
def update_book_content(cid):
    bc = BookContent.query.get_or_404(cid)
    data = request.get_json(force=True) or {}
    for field in ('book_id', 'chapter', 'page', 'paragraph', 'line', 'content'):
        if field in data:
            setattr(bc, field, data[field])
    db.session.commit()
    return _ok(bc.to_dict())


@api_bp.route('/book-content/<int:cid>', methods=['DELETE'])
def delete_book_content(cid):
    bc = BookContent.query.get_or_404(cid)
    db.session.delete(bc)
    db.session.commit()
    return _ok(msg='Content deleted')


# ── Commentary ────────────────────────────────────────────────────────────────

@api_bp.route('/commentary', methods=['GET'])
def list_commentary():
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page')
    q = Commentary.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    if page:
        q = q.filter_by(page=page)
    return jsonify([c.to_dict() for c in q.order_by(Commentary.created_at.desc()).all()])


@api_bp.route('/commentary', methods=['POST'])
def create_commentary():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('commentary_text'):
        return _err('book_id and commentary_text are required')
    c = Commentary(
        book_id=data['book_id'],
        chapter=data.get('chapter'),
        page=data.get('page'),
        paragraph=data.get('paragraph'),
        line=data.get('line'),
        commentary_text=data['commentary_text'],
    )
    db.session.add(c)
    db.session.commit()
    return _ok(c.to_dict(), 'Commentary created'), 201


@api_bp.route('/commentary/<int:cid>', methods=['GET'])
def get_commentary(cid):
    return jsonify(Commentary.query.get_or_404(cid).to_dict())


@api_bp.route('/commentary/<int:cid>', methods=['PUT'])
def update_commentary(cid):
    c = Commentary.query.get_or_404(cid)
    data = request.get_json(force=True) or {}
    for field in ('book_id', 'chapter', 'page', 'paragraph', 'line', 'commentary_text'):
        if field in data:
            setattr(c, field, data[field])
    c.updated_at = datetime.utcnow()
    db.session.commit()
    return _ok(c.to_dict())


@api_bp.route('/commentary/<int:cid>', methods=['DELETE'])
def delete_commentary(cid):
    c = Commentary.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    return _ok(msg='Commentary deleted')


# ── Sources ───────────────────────────────────────────────────────────────────

@api_bp.route('/sources', methods=['GET'])
def list_sources():
    source_type = request.args.get('type')
    q = Source.query
    if source_type:
        q = q.filter_by(source_type=source_type)
    return jsonify([s.to_dict() for s in q.order_by(Source.name).all()])


@api_bp.route('/sources', methods=['POST'])
def create_source():
    data = request.get_json(force=True) or {}
    if not data.get('name'):
        return _err('name is required')
    s = Source(
        name=data['name'],
        source_type=data.get('source_type', 'other'),
        url=data.get('url'),
        author=data.get('author'),
        publication=data.get('publication'),
        publish_date=data.get('publish_date'),
        notes=data.get('notes'),
    )
    db.session.add(s)
    db.session.commit()
    return _ok(s.to_dict(), 'Source created'), 201


@api_bp.route('/sources/<int:sid>', methods=['GET'])
def get_source(sid):
    return jsonify(Source.query.get_or_404(sid).to_dict())


@api_bp.route('/sources/<int:sid>', methods=['PUT'])
def update_source(sid):
    s = Source.query.get_or_404(sid)
    data = request.get_json(force=True) or {}
    for field in ('name', 'source_type', 'url', 'author', 'publication', 'publish_date', 'notes'):
        if field in data:
            setattr(s, field, data[field])
    db.session.commit()
    return _ok(s.to_dict())


@api_bp.route('/sources/<int:sid>', methods=['DELETE'])
def delete_source(sid):
    s = Source.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    return _ok(msg='Source deleted')


# ── Page summary ──────────────────────────────────────────────────────────────

@api_bp.route('/page-summary', methods=['GET'])
def page_summary():
    """Return all annotations for a specific book page."""
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page', '')
    if not book_id or not page:
        return _err('book_id and page are required')

    content = [c.to_dict() for c in
               BookContent.query.filter_by(book_id=book_id, page=page)
               .order_by(BookContent.paragraph, BookContent.line).all()]

    commentary = [c.to_dict() for c in
                  Commentary.query.filter_by(book_id=book_id, page=page)
                  .order_by(Commentary.created_at).all()]

    refs = [r.to_dict() for r in
            BookReference.query.filter(
                BookReference.source_book_id == book_id,
                BookReference.source_page == page
            ).order_by(BookReference.created_at).all()]

    # Dictionary lookups via book locations
    locs = BookLocation.query.filter_by(book_id=book_id, page=page).all()
    loc_ids = [l.id for l in locs]
    dict_lookups = []
    if loc_ids:
        lookups = DictionaryLookup.query.filter(
            DictionaryLookup.book_location_id.in_(loc_ids)
        ).all()
        dict_lookups = [lk.to_dict() for lk in lookups]

    return jsonify({
        'content': content,
        'commentary': commentary,
        'references': refs,
        'dictionary': dict_lookups,
    })

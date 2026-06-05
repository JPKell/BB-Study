"""
REST API – all responses are JSON.
Convention: POST = create, PUT = update, DELETE = delete.
"""
from datetime import datetime
from collections import defaultdict
from flask import Blueprint, jsonify, request
from ..models import (Setting, Book, Pamphlet, PamphletContent, Dictionary, BookLocation,
                      DictionaryLookup, BookReference, BookContent, BookContentFormat,
                      BookPageFormat, BookTableOfContents, ContentTopic, Commentary, Source,
                      SourceUrl, Topic)
from ..page_numbers import populate_book_relative_page_numbers
from .. import db

api_bp = Blueprint('api', __name__)
CONTENT_FORMAT_ROLES = {'body', 'title', 'subtitle', 'chapter', 'header', 'poetry'}
CONTENT_FORMAT_ALIGNMENTS = {'', 'left', 'center', 'right', 'justify'}


def _err(msg, code=400):
    return jsonify({'error': msg}), code


def _ok(data=None, msg='OK'):
    return jsonify({'status': 'ok', 'message': msg, 'data': data})


def _normalize_match_text(value):
    return ' '.join((value or '').lower().split())


def _page_sort_key(page):
    page = str(page or '')
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
    if total:
        return (1, total)
    return (3, page)


def _combine_content_fragments(rows):
    text = ''
    for row in rows:
        part = row.content or ''
        if not part:
            continue
        if not text:
            text = part
        elif text.endswith('-'):
            text = text[:-1] + part
        else:
            text = f'{text} {part}'
    return ' '.join(text.split())


def _content_range_bounds(start_id, end_id=None):
    start_id = int(start_id)
    end_id = int(end_id if end_id is not None else start_id)
    return min(start_id, end_id), max(start_id, end_id)


def _content_range_rows(start_id, end_id=None):
    low_id, high_id = _content_range_bounds(start_id, end_id)
    return (BookContent.query
            .filter(BookContent.id >= low_id, BookContent.id <= high_id)
            .order_by(BookContent.id)
            .all())


def _content_range_text(start_id, end_id=None):
    return _combine_content_fragments(_content_range_rows(start_id, end_id))


def _rank_value(row):
    rank = getattr(row, 'rank', None)
    if rank is None or rank < 1:
        return 1000000
    return rank


def _row_order_value(row):
    created_at = getattr(row, 'created_at', None) or datetime.min
    return (created_at, getattr(row, 'id', 0) or 0)


def _parse_rank(value):
    if value in (None, ''):
        return None
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, rank)


def _source_url_values(data):
    urls = data.get('urls')
    if urls is None:
        urls = [data.get('url')]
    cleaned = []
    seen = set()
    for value in urls or []:
        url = str(value or '').strip()
        if not url or url in seen:
            continue
        cleaned.append(url)
        seen.add(url)
    return cleaned


def _sync_source_urls(source, urls):
    source.url = urls[0] if urls else None
    source.urls[:] = [
        SourceUrl(url=url, sort_order=index)
        for index, url in enumerate(urls)
    ]


def _apply_rank(row, scope_query, requested_rank=None):
    scope_rows = scope_query.all() if hasattr(scope_query, 'all') else scope_query
    rows = [item for item in scope_rows if not _same_rank_row(item, row)]
    rows.sort(key=lambda item: (_rank_value(item), *_row_order_value(item)))
    rank = _parse_rank(requested_rank)
    if rank is None:
        rank = _rank_value(row)
        if rank >= 1000000:
            rank = len(rows) + 1
    rank = min(rank, len(rows) + 1)
    rows.insert(rank - 1, row)
    for index, item in enumerate(rows, start=1):
        item.rank = index


def _same_rank_row(left, right):
    return left.__class__ is right.__class__ and getattr(left, 'id', None) == getattr(right, 'id', None)


def _dictionary_rank_scope(book_id, page):
    return (DictionaryLookup.query
            .join(BookLocation)
            .filter(BookLocation.book_id == book_id, BookLocation.page == page))


def _topic_rank_scope(book_id, page):
    return (ContentTopic.query
            .join(BookContent, ContentTopic.book_content_id == BookContent.id)
            .filter(BookContent.book_id == book_id, BookContent.page == page))


def _page_annotation_rank_scope(book_id, page):
    if not book_id or page in (None, ''):
        return []
    rows = list(Commentary.query.filter_by(book_id=book_id, page=page).all())
    rows.extend(BookReference.query.filter(BookReference.source_book_id == book_id,
                                           BookReference.source_page == page).all())
    rows.extend(Source.query.filter_by(book_id=book_id, page=page).all())
    rows.extend(_dictionary_rank_scope(book_id, page).all())
    rows.extend(_topic_rank_scope(book_id, page).all())
    return rows


def _sync_location_from_line_text(location):
    """Find imported content matching a location's line text and refresh fields."""
    if not location.book_id or not location.line_text:
        return False

    needle = _normalize_match_text(location.line_text)
    if not needle:
        return False

    rows = (BookContent.query
            .filter_by(book_id=location.book_id)
            .order_by(BookContent.page, BookContent.paragraph, BookContent.verse,
                      BookContent.line, BookContent.id)
            .all())

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.page, row.paragraph, row.verse)].append(row)

    for group_rows in grouped.values():
        full_text = _combine_content_fragments(group_rows)
        if _normalize_match_text(full_text) == needle:
            first = group_rows[0]
            location.chapter = first.chapter_name or first.chapter
            location.page = first.page
            location.paragraph = first.paragraph
            location.line_number = first.verse
            location.line_text = full_text
            return True

    for row in rows:
        if _normalize_match_text(row.content) == needle:
            location.chapter = row.chapter_name or row.chapter
            location.page = row.page
            location.paragraph = row.paragraph
            location.line_number = row.verse or row.line
            location.line_text = row.content
            return True

    return False


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
        pdf_path=data.get('pdf_path'),
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
    for field in ('title', 'author', 'isbn', 'publisher', 'publish_date', 'edition', 'notes', 'pdf_path'):
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
    q_text = (request.args.get('q') or '').strip()
    q = Pamphlet.query
    if q_text:
        like = f'%{q_text}%'
        q = q.filter(
            Pamphlet.title.ilike(like) |
            Pamphlet.series.ilike(like) |
            Pamphlet.notes.ilike(like)
        )
    return jsonify([p.to_dict() for p in q.order_by(Pamphlet.series, Pamphlet.title).all()])


@api_bp.route('/pamphlets', methods=['POST'])
def create_pamphlet():
    data = request.get_json(force=True) or {}
    if not data.get('title'):
        return _err('title is required')
    if not data.get('series'):
        return _err('series is required')
    p = Pamphlet(
        title=data['title'],
        series=data['series'],
        publisher=data.get('publisher') or 'AA World Services',
        pdf_path=data.get('pdf_path'),
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
    for field in ('title', 'publisher', 'series', 'pdf_path', 'notes'):
        if field in data:
            setattr(p, field, data[field])
    if not p.publisher:
        p.publisher = 'AA World Services'
    db.session.commit()
    return _ok(p.to_dict())


@api_bp.route('/pamphlets/<int:pid>', methods=['DELETE'])
def delete_pamphlet(pid):
    p = Pamphlet.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return _ok(msg='Pamphlet deleted')


@api_bp.route('/pamphlets/<int:pid>/content', methods=['GET'])
def list_pamphlet_content(pid):
    Pamphlet.query.get_or_404(pid)
    rows = PamphletContent.query.filter_by(pamphlet_id=pid).all()
    rows.sort(key=lambda row: (_page_sort_key(row.page), row.paragraph or 0,
                               row.line or 0, row.id))
    return jsonify([row.to_dict() for row in rows])


@api_bp.route('/pamphlet-content/<int:cid>', methods=['PUT'])
def update_pamphlet_content(cid):
    row = PamphletContent.query.get_or_404(cid)
    data = request.get_json(force=True) or {}
    if 'content' in data:
        row.content = data['content']
    db.session.commit()
    return _ok(row.to_dict())


@api_bp.route('/pamphlets/search', methods=['GET'])
def search_pamphlets():
    query_text = (request.args.get('q') or '').strip()
    limit = min(request.args.get('limit', 30, type=int), 100)
    if not query_text:
        return jsonify([])

    needle = _normalize_match_text(query_text)
    matched = {}
    meta_like = f'%{query_text}%'
    for pamphlet in Pamphlet.query.filter(
        Pamphlet.title.ilike(meta_like) |
        Pamphlet.series.ilike(meta_like) |
        Pamphlet.notes.ilike(meta_like)
    ).order_by(Pamphlet.series, Pamphlet.title).limit(limit).all():
        matched[pamphlet.id] = {
            'pamphlet': pamphlet,
            'excerpt': pamphlet.notes or pamphlet.title,
            'page': None,
        }

    rows = (PamphletContent.query
            .join(Pamphlet)
            .order_by(Pamphlet.series, Pamphlet.title, PamphletContent.page,
                      PamphletContent.paragraph, PamphletContent.line, PamphletContent.id)
            .all())
    for row in rows:
        if row.pamphlet_id in matched:
            continue
        if needle in _normalize_match_text(row.content):
            matched[row.pamphlet_id] = {
                'pamphlet': row.pamphlet,
                'excerpt': row.content,
                'page': row.page,
            }
            if len(matched) >= limit:
                break

    return jsonify([{
        'id': item['pamphlet'].id,
        'title': item['pamphlet'].title,
        'series': item['pamphlet'].series,
        'publisher': item['pamphlet'].publisher,
        'pdf_path': item['pamphlet'].pdf_path,
        'page': item['page'],
        'excerpt': item['excerpt'],
    } for item in matched.values()])


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


# ── Topics / Tags ────────────────────────────────────────────────────────────

@api_bp.route('/topics', methods=['GET'])
def list_topics():
    q = request.args.get('q', '').strip()
    query = Topic.query
    if q:
        query = query.filter(Topic.name.ilike(f'%{q}%'))
    return jsonify([topic.to_dict() for topic in query.order_by(Topic.name).all()])


@api_bp.route('/topics', methods=['POST'])
def create_topic():
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return _err('name is required')
    existing = Topic.query.filter(Topic.name.ilike(name)).first()
    if existing:
        return _ok(existing.to_dict(), 'Topic already exists')
    topic = Topic(name=name, description=data.get('description'))
    db.session.add(topic)
    db.session.commit()
    return _ok(topic.to_dict(), 'Topic created'), 201


@api_bp.route('/topics/<int:topic_id>', methods=['PUT'])
def update_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    data = request.get_json(force=True) or {}
    if 'name' in data:
        topic.name = data['name'].strip()
    if 'description' in data:
        topic.description = data['description']
    db.session.commit()
    return _ok(topic.to_dict())


@api_bp.route('/topics/<int:topic_id>', methods=['DELETE'])
def delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    db.session.delete(topic)
    db.session.commit()
    return _ok(msg='Topic deleted')


@api_bp.route('/content-topics', methods=['GET'])
def list_content_topics():
    topic_id = request.args.get('topic_id', type=int)
    book_content_id = request.args.get('book_content_id', type=int)
    q = ContentTopic.query
    if topic_id:
        q = q.filter_by(topic_id=topic_id)
    if book_content_id:
        q = q.filter(
            db.func.min(
                db.func.coalesce(ContentTopic.start_content_id, ContentTopic.book_content_id),
                db.func.coalesce(ContentTopic.end_content_id, ContentTopic.book_content_id)
            ) <= book_content_id,
            db.func.max(
                db.func.coalesce(ContentTopic.start_content_id, ContentTopic.book_content_id),
                db.func.coalesce(ContentTopic.end_content_id, ContentTopic.book_content_id)
            ) >= book_content_id,
        )
    return jsonify([link.to_dict() for link in q.order_by(ContentTopic.created_at.desc()).all()])


@api_bp.route('/content-topics', methods=['POST'])
def create_content_topic():
    data = request.get_json(force=True) or {}
    topic_id = data.get('topic_id')
    content_ids = data.get('content_ids') or []
    start_content_id = data.get('start_content_id')
    end_content_id = data.get('end_content_id')
    notes = data.get('notes')
    if content_ids and not start_content_id:
        parsed_ids = [int(content_id) for content_id in content_ids if content_id]
        if parsed_ids:
            start_content_id = min(parsed_ids)
            end_content_id = max(parsed_ids)
    if not topic_id or not start_content_id:
        return _err('topic_id and start_content_id are required')
    if not end_content_id:
        end_content_id = start_content_id
    Topic.query.get_or_404(topic_id)
    low_id, high_id = _content_range_bounds(start_content_id, end_content_id)
    start = BookContent.query.get_or_404(low_id)
    BookContent.query.get_or_404(high_id)
    link = ContentTopic.query.filter_by(
        topic_id=topic_id,
        book_content_id=low_id,
        start_content_id=low_id,
        end_content_id=high_id,
    ).first()
    if not link:
        link = ContentTopic(
            topic_id=topic_id,
            book_content_id=low_id,
            start_content_id=low_id,
            end_content_id=high_id,
            notes=notes,
        )
        db.session.add(link)
        db.session.flush()
    elif notes is not None:
        link.notes = notes
    _apply_rank(link, _page_annotation_rank_scope(start.book_id, start.page), data.get('rank'))
    db.session.commit()
    return _ok(link.to_dict(), 'Topic applied')


@api_bp.route('/content-topics/<int:link_id>', methods=['DELETE'])
def delete_content_topic(link_id):
    link = ContentTopic.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    return _ok(msg='Content topic deleted')


@api_bp.route('/book-content/range', methods=['GET'])
def get_book_content_range():
    start_id = request.args.get('start_id', type=int)
    end_id = request.args.get('end_id', type=int)
    if not start_id:
        return _err('start_id is required')
    rows = _content_range_rows(start_id, end_id or start_id)
    if not rows:
        return _err('No content found for range', 404)
    first = rows[0]
    last = rows[-1]
    return jsonify({
        'start_content_id': first.id,
        'end_content_id': last.id,
        'low_content_id': first.id,
        'high_content_id': last.id,
        'book_id': first.book_id,
        'book_title': first.book.title if first.book else None,
        'chapter_name': first.chapter_name or first.chapter,
        'page': first.page,
        'paragraph': first.paragraph,
        'line': first.line,
        'verse': first.verse,
        'end_page': last.page,
        'end_paragraph': last.paragraph,
        'end_line': last.line,
        'end_verse': last.verse,
        'content': _combine_content_fragments(rows),
        'content_ids': [row.id for row in rows],
    })


@api_bp.route('/content-topics/<int:link_id>', methods=['GET'])
def get_content_topic(link_id):
    return jsonify(ContentTopic.query.get_or_404(link_id).to_dict())


@api_bp.route('/content-topics/<int:link_id>', methods=['PUT'])
def update_content_topic(link_id):
    link = ContentTopic.query.get_or_404(link_id)
    data = request.get_json(force=True) or {}

    if 'topic_id' in data:
        topic_id = data.get('topic_id')
        if not topic_id:
            return _err('topic_id is required')
        Topic.query.get_or_404(topic_id)

        link.topic_id = topic_id

    if 'start_content_id' in data or 'end_content_id' in data or 'content_ids' in data:
        start_content_id = data.get('start_content_id') or link.start_content_id or link.book_content_id
        end_content_id = data.get('end_content_id') or link.end_content_id or start_content_id
        content_ids = data.get('content_ids') or []
        if content_ids:
            parsed_ids = [int(content_id) for content_id in content_ids if content_id]
            if parsed_ids:
                start_content_id = min(parsed_ids)
                end_content_id = max(parsed_ids)
        low_id, high_id = _content_range_bounds(start_content_id, end_content_id)
        BookContent.query.get_or_404(low_id)
        BookContent.query.get_or_404(high_id)
        link.book_content_id = low_id
        link.start_content_id = low_id
        link.end_content_id = high_id

    if 'notes' in data:
        link.notes = data.get('notes')

    content = BookContent.query.get(link.book_content_id)
    if content and ('rank' in data or link.rank is None):
        _apply_rank(link, _page_annotation_rank_scope(content.book_id, content.page), data.get('rank'))

    db.session.commit()
    return _ok(link.to_dict(), 'Content topic updated')


@api_bp.route('/search', methods=['GET'])
def search_content():
    query_text = (request.args.get('q') or '').strip()
    topic_id = request.args.get('topic_id', type=int)
    book_id = request.args.get('book_id', type=int)
    limit = min(request.args.get('limit', 50, type=int), 200)
    if not query_text and not topic_id:
        return jsonify([])

    rows_query = BookContent.query
    if book_id:
        rows_query = rows_query.filter_by(book_id=book_id)
    rows = rows_query.order_by(BookContent.book_id, BookContent.page, BookContent.paragraph,
                               BookContent.verse, BookContent.line, BookContent.id).all()

    tagged_ranges = []
    topic_name_matches = []
    if topic_id:
        links = ContentTopic.query.filter_by(topic_id=topic_id).all()
        tagged_ranges = [
            _content_range_bounds(link.start_content_id or link.book_content_id,
                                  link.end_content_id or link.book_content_id)
            for link in links
        ]
    elif query_text:
        topic_name_matches = Topic.query.filter(Topic.name.ilike(f'%{query_text}%')).all()
        if topic_name_matches:
            topic_ids = [topic.id for topic in topic_name_matches]
            links = ContentTopic.query.filter(ContentTopic.topic_id.in_(topic_ids)).all()
            tagged_ranges = [
                _content_range_bounds(link.start_content_id or link.book_content_id,
                                      link.end_content_id or link.book_content_id)
                for link in links
            ]

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.book_id, row.page, row.paragraph, row.verse)].append(row)

    results = []
    needle = _normalize_match_text(query_text)
    for group_rows in grouped.values():
        verse_text = _combine_content_fragments(group_rows)
        normalized = _normalize_match_text(verse_text)
        content_ids = [row.id for row in group_rows]
        text_matches = bool(needle and needle in normalized)
        tag_matches = bool(tagged_ranges and any(
            low_id <= content_id <= high_id
            for content_id in content_ids
            for low_id, high_id in tagged_ranges
        ))
        if not text_matches and not tag_matches:
            continue

        first = group_rows[0]
        all_links = ContentTopic.query.all()
        topics = []
        seen_topics = set()
        for link in all_links:
            low_id, high_id = _content_range_bounds(
                link.start_content_id or link.book_content_id,
                link.end_content_id or link.book_content_id,
            )
            if not any(low_id <= content_id <= high_id for content_id in content_ids):
                continue
            if link.topic_id not in seen_topics:
                seen_topics.add(link.topic_id)
                topics.append({'id': link.topic_id, 'name': link.topic.name if link.topic else ''})

        results.append({
            'book_id': first.book_id,
            'book_title': first.book.title if first.book else None,
            'chapter_number': first.chapter_number,
            'chapter_name': first.chapter_name or first.chapter,
            'page': first.page,
            'paragraph': first.paragraph,
            'verse': first.verse,
            'line': first.line,
            'excerpt': verse_text,
            'content_ids': content_ids,
            'topics': topics,
            'match_type': 'text+tag' if text_matches and tag_matches else ('text' if text_matches else 'tag'),
        })
        if len(results) >= limit:
            break

    if query_text and not book_id and len(results) < limit:
        pamphlet_hits = []
        rows = (PamphletContent.query
                .join(Pamphlet)
                .order_by(Pamphlet.series, Pamphlet.title, PamphletContent.page,
                          PamphletContent.paragraph, PamphletContent.line, PamphletContent.id)
                .all())
        seen_pamphlets = set()
        for row in rows:
            if row.pamphlet_id in seen_pamphlets:
                continue
            if needle in _normalize_match_text(row.content):
                seen_pamphlets.add(row.pamphlet_id)
                pamphlet_hits.append({
                    'result_type': 'pamphlet',
                    'pamphlet_id': row.pamphlet_id,
                    'pamphlet_title': row.pamphlet.title if row.pamphlet else None,
                    'series': row.pamphlet.series if row.pamphlet else None,
                    'publisher': row.pamphlet.publisher if row.pamphlet else None,
                    'page': row.page,
                    'paragraph': row.paragraph,
                    'line': row.line,
                    'excerpt': row.content,
                    'match_type': 'pamphlet',
                })
                if len(results) + len(pamphlet_hits) >= limit:
                    break

        if len(results) + len(pamphlet_hits) < limit:
            meta_like = f'%{query_text}%'
            for pamphlet in Pamphlet.query.filter(
                Pamphlet.title.ilike(meta_like) |
                Pamphlet.series.ilike(meta_like) |
                Pamphlet.notes.ilike(meta_like)
            ).order_by(Pamphlet.series, Pamphlet.title).all():
                if pamphlet.id in seen_pamphlets:
                    continue
                seen_pamphlets.add(pamphlet.id)
                pamphlet_hits.append({
                    'result_type': 'pamphlet',
                    'pamphlet_id': pamphlet.id,
                    'pamphlet_title': pamphlet.title,
                    'series': pamphlet.series,
                    'publisher': pamphlet.publisher,
                    'page': None,
                    'paragraph': None,
                    'line': None,
                    'excerpt': pamphlet.notes or pamphlet.title,
                    'match_type': 'pamphlet',
                })
                if len(results) + len(pamphlet_hits) >= limit:
                    break

        results.extend(pamphlet_hits)

    return jsonify(results)


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
    matched = _sync_location_from_line_text(loc)
    db.session.add(loc)
    db.session.commit()
    result = loc.to_dict()
    result['line_text_matched'] = matched
    return _ok(result, 'Location created'), 201


@api_bp.route('/book-locations/<int:lid>', methods=['PUT'])
def update_book_location(lid):
    loc = BookLocation.query.get_or_404(lid)
    data = request.get_json(force=True) or {}
    should_sync = 'line_text' in data or 'book_id' in data
    for field in ('book_id', 'chapter', 'page', 'paragraph', 'line_number', 'line_text'):
        if field in data:
            setattr(loc, field, data[field])
    matched = _sync_location_from_line_text(loc) if should_sync else False
    db.session.commit()
    result = loc.to_dict()
    result['line_text_matched'] = matched
    return _ok(result)


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
    db.session.flush()
    location = lk.location
    if location:
        _apply_rank(lk, _page_annotation_rank_scope(location.book_id, location.page), data.get('rank'))
    db.session.commit()
    return _ok(lk.to_dict(), 'Lookup created'), 201


@api_bp.route('/dictionary-lookup/<int:lid>', methods=['GET'])
def get_dictionary_lookup(lid):
    return jsonify(DictionaryLookup.query.get_or_404(lid).to_dict())


@api_bp.route('/dictionary-lookup/<int:lid>', methods=['PUT'])
def update_dictionary_lookup(lid):
    lk = DictionaryLookup.query.get_or_404(lid)
    data = request.get_json(force=True) or {}
    if 'dictionary_id' in data:
        lk.dictionary_id = data.get('dictionary_id')
    if 'book_location_id' in data:
        lk.book_location_id = data.get('book_location_id')
    db.session.flush()
    location = lk.location
    if location and ('rank' in data or lk.rank is None):
        _apply_rank(lk, _page_annotation_rank_scope(location.book_id, location.page), data.get('rank'))
    db.session.commit()
    return _ok(lk.to_dict())


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
        source_verse=data.get('source_verse', data.get('source_line')),
        target_book_id=data['target_book_id'],
        target_chapter=data.get('target_chapter'),
        target_page=data.get('target_page'),
        target_paragraph=data.get('target_paragraph'),
        target_verse=data.get('target_verse', data.get('target_line')),
        quoted_text=data.get('quoted_text'),
        comments=data.get('comments'),
    )
    db.session.add(ref)
    db.session.flush()
    _apply_rank(ref, _page_annotation_rank_scope(ref.source_book_id, ref.source_page), data.get('rank'))
    db.session.commit()
    return _ok(ref.to_dict(), 'Reference created'), 201


@api_bp.route('/references/<int:rid>', methods=['GET'])
def get_reference(rid):
    return jsonify(BookReference.query.get_or_404(rid).to_dict())


@api_bp.route('/references/<int:rid>', methods=['PUT'])
def update_reference(rid):
    ref = BookReference.query.get_or_404(rid)
    data = request.get_json(force=True) or {}
    field_aliases = {'source_line': 'source_verse', 'target_line': 'target_verse'}
    fields = ('source_book_id', 'source_chapter', 'source_page', 'source_paragraph',
              'source_verse', 'source_line', 'target_book_id', 'target_chapter',
              'target_page', 'target_paragraph', 'target_verse', 'target_line',
              'quoted_text', 'comments', 'rank')
    for field in fields:
        if field in data and field != 'rank':
            setattr(ref, field_aliases.get(field, field), data[field])
    if 'rank' in data or ref.rank is None:
        _apply_rank(ref, _page_annotation_rank_scope(ref.source_book_id, ref.source_page), data.get('rank'))
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
    chapter_name = request.args.get('chapter_name')
    content_mode = request.args.get('content_mode')
    q = BookContent.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    if page:
        q = q.filter_by(page=page)
    if chapter:
        q = q.filter_by(chapter_name=chapter)
    if chapter_name:
        q = q.filter_by(chapter_name=chapter_name)
    if content_mode:
        q = q.filter_by(content_mode=content_mode)
    results = q.order_by(BookContent.chapter_number, BookContent.chapter_name, BookContent.relative_page_number,
                         BookContent.page,
                         BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id).all()
    return jsonify([r.to_dict() for r in results])


@api_bp.route('/book-content', methods=['POST'])
def create_book_content():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('content'):
        return _err('book_id and content are required')
    bc = BookContent(
        book_id=data['book_id'],
        content_mode=data.get('content_mode', 'sentence'),
        chapter_number=data.get('chapter_number'),
        chapter_name=data.get('chapter_name') or data.get('chapter'),
        chapter=data.get('chapter_name') or data.get('chapter'),
        page=data.get('page'),
        paragraph=data.get('paragraph'),
        line=data.get('line'),
        verse=data.get('verse'),
        content=data['content'],
    )
    db.session.add(bc)
    db.session.commit()
    populate_book_relative_page_numbers(bc.book_id)
    return _ok(bc.to_dict(), 'Content created'), 201


@api_bp.route('/book-content/<int:cid>', methods=['GET'])
def get_book_content(cid):
    return jsonify(BookContent.query.get_or_404(cid).to_dict())


@api_bp.route('/book-content/<int:cid>', methods=['PUT'])
def update_book_content(cid):
    bc = BookContent.query.get_or_404(cid)
    original_book_id = bc.book_id
    data = request.get_json(force=True) or {}
    for field in ('book_id', 'content_mode', 'chapter_number', 'chapter_name', 'chapter', 'page', 'paragraph', 'line', 'verse', 'content'):
        if field in data:
            setattr(bc, field, data[field])
    if 'chapter_name' in data and 'chapter' not in data:
        bc.chapter = data['chapter_name']
    db.session.commit()
    populate_book_relative_page_numbers(bc.book_id)
    if original_book_id != bc.book_id:
        populate_book_relative_page_numbers(original_book_id)
    return _ok(bc.to_dict())


@api_bp.route('/book-content/<int:cid>/split', methods=['POST'])
def split_book_content(cid):
    bc = BookContent.query.get_or_404(cid)
    data = request.get_json(force=True) or {}
    left, right = _split_content_parts(bc.content or '', data)
    if not left or not right:
        return _err('Both sides of the split must contain text')

    original_format = None
    if bc.verse is not None:
        original_format = BookContentFormat.query.filter_by(
            book_id=bc.book_id,
            page=bc.page,
            paragraph=bc.paragraph,
            verse=bc.verse,
        ).first()

    new_verse = None
    new_line = bc.line
    if bc.verse is not None:
        new_verse = bc.verse + 1
        continuation_rows = _same_verse_rows_after(bc)
        _shift_book_content_verses(bc.book_id, bc.page, bc.paragraph, bc.verse)
        for row in continuation_rows:
            row.verse = new_verse
    elif bc.line is not None:
        new_line = bc.line + 1
        _shift_book_content_lines(bc.book_id, bc.page, bc.paragraph, bc.line)
    else:
        return _err('Selected content must have a verse or line number to split')

    bc.content = left
    new_row = BookContent(
        book_id=bc.book_id,
        content_mode=bc.content_mode,
        chapter_number=bc.chapter_number,
        chapter_name=bc.chapter_name,
        chapter=bc.chapter,
        page=bc.page,
        paragraph=bc.paragraph,
        line=new_line,
        verse=new_verse,
        content=right,
    )
    db.session.add(new_row)
    db.session.flush()

    if original_format and new_verse is not None:
        db.session.add(BookContentFormat(
            book_id=bc.book_id,
            page=bc.page,
            paragraph=bc.paragraph,
            verse=new_verse,
            is_bold=original_format.is_bold,
            is_italic=original_format.is_italic,
            content_role=original_format.content_role or 'body',
            alignment_override=original_format.alignment_override,
        ))

    db.session.commit()
    populate_book_relative_page_numbers(bc.book_id)
    return _ok({'left': bc.to_dict(), 'right': new_row.to_dict()}, 'Content split')


def _same_verse_rows_after(row):
    if row.verse is None:
        return []
    rows = (BookContent.query
            .filter(BookContent.book_id == row.book_id,
                    BookContent.page == row.page,
                    BookContent.paragraph == row.paragraph,
                    BookContent.verse == row.verse,
                    BookContent.id != row.id)
            .order_by(BookContent.line, BookContent.id)
            .all())

    def after_split(candidate):
        if row.line is None or candidate.line is None:
            return candidate.id > row.id
        return (candidate.line, candidate.id) > (row.line, row.id)

    return [candidate for candidate in rows if after_split(candidate)]


def _split_content_parts(original, data):
    marker_text = data.get('marker_text')
    if marker_text is not None:
        if str(marker_text).count('|') != 1:
            return '', ''
        left, right = str(marker_text).split('|', 1)
        return left.strip(), right.strip()

    if 'left' in data or 'right' in data:
        return str(data.get('left') or '').strip(), str(data.get('right') or '').strip()

    try:
        offset = int(data.get('offset'))
    except (TypeError, ValueError):
        return '', ''
    if offset <= 0 or offset >= len(original):
        return '', ''
    return original[:offset].strip(), original[offset:].strip()


def _shift_book_content_verses(book_id, page, paragraph, after_verse):
    rows = (BookContent.query
            .filter(BookContent.book_id == book_id,
                    BookContent.page == page,
                    BookContent.paragraph == paragraph,
                    BookContent.verse > after_verse)
            .order_by(BookContent.verse.desc(), BookContent.id.desc())
            .all())
    for row in rows:
        row.verse += 1

    formats = (BookContentFormat.query
               .filter(BookContentFormat.book_id == book_id,
                       BookContentFormat.page == page,
                       BookContentFormat.paragraph == paragraph,
                       BookContentFormat.verse > after_verse)
               .order_by(BookContentFormat.verse.desc(), BookContentFormat.id.desc())
               .all())
    for fmt in formats:
        fmt.verse += 1
        db.session.flush()

    for row in Commentary.query.filter(Commentary.book_id == book_id,
                                       Commentary.page == page,
                                       Commentary.paragraph == paragraph,
                                       Commentary.verse > after_verse).all():
        row.verse += 1

    for row in Source.query.filter(Source.book_id == book_id,
                                   Source.page == page,
                                   Source.paragraph == paragraph,
                                   Source.verse > after_verse).all():
        row.verse += 1

    for row in BookReference.query.filter(BookReference.source_book_id == book_id,
                                          BookReference.source_page == page,
                                          BookReference.source_paragraph == paragraph,
                                          BookReference.source_verse > after_verse).all():
        row.source_verse += 1

    for row in BookReference.query.filter(BookReference.target_book_id == book_id,
                                          BookReference.target_page == page,
                                          BookReference.target_paragraph == paragraph,
                                          BookReference.target_verse > after_verse).all():
        row.target_verse += 1

    for location in BookLocation.query.filter(BookLocation.book_id == book_id,
                                              BookLocation.page == page,
                                              BookLocation.paragraph == paragraph,
                                              BookLocation.line_number > after_verse).all():
        location.line_number += 1


def _shift_book_content_lines(book_id, page, paragraph, after_line):
    rows = (BookContent.query
            .filter(BookContent.book_id == book_id,
                    BookContent.page == page,
                    BookContent.paragraph == paragraph,
                    BookContent.line > after_line)
            .order_by(BookContent.line.desc(), BookContent.id.desc())
            .all())
    for row in rows:
        row.line += 1


@api_bp.route('/book-content/<int:cid>', methods=['DELETE'])
def delete_book_content(cid):
    bc = BookContent.query.get_or_404(cid)
    db.session.delete(bc)
    db.session.commit()
    return _ok(msg='Content deleted')


@api_bp.route('/book-content-formats', methods=['GET'])
def list_book_content_formats():
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page')
    q = BookContentFormat.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    if page:
        q = q.filter_by(page=page)
    return jsonify([fmt.to_dict() for fmt in q.order_by(
        BookContentFormat.page, BookContentFormat.paragraph, BookContentFormat.verse
    ).all()])


@api_bp.route('/book-content-formats', methods=['PUT'])
def upsert_book_content_format():
    data = request.get_json(force=True) or {}
    required = ('book_id', 'page', 'paragraph', 'verse')
    if any(data.get(field) in (None, '') for field in required):
        return _err('book_id, page, paragraph, and verse are required')

    book_id = int(data['book_id'])
    paragraph = int(data['paragraph'])
    verse = int(data['verse'])
    page = str(data['page'])
    is_bold = bool(data.get('is_bold', False))
    is_italic = bool(data.get('is_italic', False))
    content_role = data.get('content_role') or 'body'
    if content_role not in CONTENT_FORMAT_ROLES:
        return _err('content_role must be body, title, subtitle, chapter, header, or poetry')
    alignment_override = data.get('alignment_override') or ''
    if alignment_override not in CONTENT_FORMAT_ALIGNMENTS:
        return _err('alignment_override must be default, left, center, right, or justify')

    fmt = BookContentFormat.query.filter_by(
        book_id=book_id, page=page, paragraph=paragraph, verse=verse
    ).first()

    if not is_bold and not is_italic and content_role == 'body' and not alignment_override:
        if fmt:
            db.session.delete(fmt)
            db.session.commit()
        return _ok({
            'book_id': book_id,
            'page': page,
            'paragraph': paragraph,
            'verse': verse,
            'is_bold': False,
            'is_italic': False,
            'content_role': 'body',
            'alignment_override': '',
        }, 'Content format cleared')

    if not fmt:
        fmt = BookContentFormat(book_id=book_id, page=page, paragraph=paragraph, verse=verse)
        db.session.add(fmt)
    fmt.is_bold = is_bold
    fmt.is_italic = is_italic
    fmt.content_role = content_role
    fmt.alignment_override = alignment_override or None
    db.session.commit()
    return _ok(fmt.to_dict(), 'Content format saved')


@api_bp.route('/book-page-format', methods=['GET'])
def get_book_page_format():
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page', type=str)
    if not book_id or not page:
        return _err('book_id and page are required')
    fmt = BookPageFormat.query.filter_by(book_id=book_id, page=str(page)).first()
    if fmt:
        return jsonify(fmt.to_dict())
    return jsonify({
        'book_id': book_id,
        'page': str(page),
        'centered_export': False,
    })


@api_bp.route('/book-page-format', methods=['PUT'])
def upsert_book_page_format():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('page'):
        return _err('book_id and page are required')
    book_id = int(data['book_id'])
    page = str(data['page'])
    centered_export = bool(data.get('centered_export', False))
    fmt = BookPageFormat.query.filter_by(book_id=book_id, page=page).first()
    if not centered_export:
        if fmt:
            db.session.delete(fmt)
            db.session.commit()
        return _ok({
            'book_id': book_id,
            'page': page,
            'centered_export': False,
        }, 'Page format cleared')
    if not fmt:
        fmt = BookPageFormat(book_id=book_id, page=page)
        db.session.add(fmt)
    fmt.centered_export = centered_export
    db.session.commit()
    return _ok(fmt.to_dict(), 'Page format saved')


# ── Book Table of Contents ───────────────────────────────────────────────────

@api_bp.route('/book-toc', methods=['GET'])
def list_book_toc():
    book_id = request.args.get('book_id', type=int)
    q = BookTableOfContents.query
    if book_id:
        q = q.filter_by(book_id=book_id)
    entries = q.order_by(BookTableOfContents.sort_order, BookTableOfContents.id).all()
    return jsonify([entry.to_dict() for entry in entries])


@api_bp.route('/book-toc', methods=['POST'])
def create_book_toc():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('title'):
        return _err('book_id and title are required')
    entry = BookTableOfContents(
        book_id=data['book_id'],
        sort_order=data.get('sort_order') or 0,
        chapter_number=data.get('chapter_number'),
        chapter_name=data.get('chapter_name') or data.get('title'),
        chapter=data.get('chapter_number') or data.get('chapter'),
        title=data['title'],
        page=data.get('page'),
        include_by_default=bool(data.get('include_by_default', True)),
    )
    db.session.add(entry)
    db.session.commit()
    return _ok(entry.to_dict(), 'Table of contents entry created'), 201


@api_bp.route('/book-toc/<int:toc_id>', methods=['PUT'])
def update_book_toc(toc_id):
    entry = BookTableOfContents.query.get_or_404(toc_id)
    data = request.get_json(force=True) or {}
    for field in ('book_id', 'sort_order', 'chapter_number', 'chapter_name', 'chapter', 'title', 'page', 'include_by_default'):
        if field in data:
            setattr(entry, field, data[field])
    if 'chapter_name' in data and 'title' not in data:
        entry.title = data['chapter_name']
    db.session.commit()
    return _ok(entry.to_dict())


@api_bp.route('/book-toc/<int:toc_id>', methods=['DELETE'])
def delete_book_toc(toc_id):
    entry = BookTableOfContents.query.get_or_404(toc_id)
    db.session.delete(entry)
    db.session.commit()
    return _ok(msg='Table of contents entry deleted')


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
    rows = q.all()
    rows.sort(key=lambda c: (_rank_value(c), *_row_order_value(c)))
    return jsonify([c.to_dict() for c in rows])


@api_bp.route('/commentary', methods=['POST'])
def create_commentary():
    data = request.get_json(force=True) or {}
    if not data.get('book_id') or not data.get('commentary_text'):
        return _err('book_id and commentary_text are required')
    Book.query.get_or_404(data['book_id'])
    c = Commentary(
        book_id=data['book_id'],
        chapter=data.get('chapter'),
        page=data.get('page'),
        paragraph=data.get('paragraph'),
        verse=data.get('verse', data.get('line')),
        commentary_text=data['commentary_text'],
    )
    db.session.add(c)
    db.session.flush()
    _apply_rank(c, _page_annotation_rank_scope(c.book_id, c.page), data.get('rank'))
    db.session.commit()
    return _ok(c.to_dict(), 'Commentary created'), 201


@api_bp.route('/commentary/<int:cid>', methods=['GET'])
def get_commentary(cid):
    return jsonify(Commentary.query.get_or_404(cid).to_dict())


@api_bp.route('/commentary/<int:cid>', methods=['PUT'])
def update_commentary(cid):
    c = Commentary.query.get_or_404(cid)
    data = request.get_json(force=True) or {}
    field_aliases = {'line': 'verse'}
    for field in ('book_id', 'chapter', 'page', 'paragraph', 'verse', 'line', 'commentary_text', 'rank'):
        if field in data and field != 'rank':
            setattr(c, field_aliases.get(field, field), data[field])
    if 'rank' in data or c.rank is None:
        _apply_rank(c, _page_annotation_rank_scope(c.book_id, c.page), data.get('rank'))
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
    book_id = request.args.get('book_id', type=int)
    page = request.args.get('page')
    q = Source.query
    if source_type:
        q = q.filter_by(source_type=source_type)
    if book_id:
        q = q.filter_by(book_id=book_id)
    if page:
        q = q.filter_by(page=page)
    rows = q.all()
    rows.sort(key=lambda s: (_rank_value(s), *_row_order_value(s)))
    return jsonify([s.to_dict() for s in rows])


@api_bp.route('/sources', methods=['POST'])
def create_source():
    data = request.get_json(force=True) or {}
    if not data.get('name'):
        return _err('name is required')
    urls = _source_url_values(data)
    s = Source(
        book_id=data.get('book_id'),
        page=data.get('page'),
        chapter=data.get('chapter'),
        paragraph=data.get('paragraph'),
        verse=data.get('verse', data.get('line')),
        name=data['name'],
        source_type=data.get('source_type', 'other'),
        url=urls[0] if urls else None,
        author=data.get('author'),
        publication=data.get('publication'),
        publish_date=data.get('publish_date'),
        notes=data.get('notes'),
    )
    _sync_source_urls(s, urls)
    db.session.add(s)
    db.session.flush()
    if s.book_id and s.page:
        _apply_rank(s, _page_annotation_rank_scope(s.book_id, s.page), data.get('rank'))
    db.session.commit()
    return _ok(s.to_dict(), 'Source created'), 201


@api_bp.route('/sources/<int:sid>', methods=['GET'])
def get_source(sid):
    return jsonify(Source.query.get_or_404(sid).to_dict())


@api_bp.route('/sources/<int:sid>', methods=['PUT'])
def update_source(sid):
    s = Source.query.get_or_404(sid)
    data = request.get_json(force=True) or {}
    field_aliases = {'line': 'verse'}
    for field in ('book_id', 'page', 'chapter', 'paragraph', 'verse', 'line',
                  'name', 'source_type', 'url', 'author', 'publication', 'publish_date', 'notes', 'rank'):
        if field in data and field != 'rank':
            setattr(s, field_aliases.get(field, field), data[field])
    if 'urls' in data or 'url' in data:
        _sync_source_urls(s, _source_url_values(data))
    if s.book_id and s.page and ('rank' in data or s.rank is None):
        _apply_rank(s, _page_annotation_rank_scope(s.book_id, s.page), data.get('rank'))
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
               .order_by(BookContent.paragraph, BookContent.line, BookContent.verse, BookContent.id).all()]

    commentary_rows = Commentary.query.filter_by(book_id=book_id, page=page).all()
    commentary_rows.sort(key=lambda c: (_rank_value(c), *_row_order_value(c)))
    commentary = [c.to_dict() for c in commentary_rows]

    ref_rows = (BookReference.query.filter(
                BookReference.source_book_id == book_id,
                BookReference.source_page == page
            ).all())
    ref_rows.sort(key=lambda r: (_rank_value(r), *_row_order_value(r)))
    refs = [r.to_dict() for r in ref_rows]

    source_rows = Source.query.filter_by(book_id=book_id, page=page).all()
    source_rows.sort(key=lambda s: (_rank_value(s), *_row_order_value(s)))
    sources = [s.to_dict() for s in source_rows]

    # Dictionary lookups via book locations
    locs = BookLocation.query.filter_by(book_id=book_id, page=page).all()
    loc_ids = [l.id for l in locs]
    dict_lookups = []
    if loc_ids:
        lookups = DictionaryLookup.query.filter(
            DictionaryLookup.book_location_id.in_(loc_ids)
        ).all()
        lookups.sort(key=lambda lk: (_rank_value(lk), lk.id or 0))
        dict_lookups = [lk.to_dict() for lk in lookups]

    content_ids = [c['id'] for c in content]
    topic_links = []
    if content_ids:
        page_low_id = min(content_ids)
        page_high_id = max(content_ids)
        links = ContentTopic.query.order_by(ContentTopic.created_at).all()
        topic_links = []
        for link in links:
            low_id, high_id = _content_range_bounds(
                link.start_content_id or link.book_content_id,
                link.end_content_id or link.book_content_id,
            )
            if low_id <= page_high_id and high_id >= page_low_id:
                topic_links.append(link)
        topic_links.sort(key=lambda link: (_rank_value(link), *_row_order_value(link)))
        topic_links = [link.to_dict() for link in topic_links]

    return jsonify({
        'content': content,
        'commentary': commentary,
        'references': refs,
        'sources': sources,
        'dictionary': dict_lookups,
        'topics': topic_links,
    })

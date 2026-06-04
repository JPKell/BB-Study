from datetime import datetime
from . import db


def _combine_model_content(rows):
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


class Setting(db.Model):
    """Application settings (theme, current book, etc.)."""
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')

    def to_dict(self):
        return {'id': self.id, 'key': self.key, 'value': self.value}


class Book(db.Model):
    """Books used as primary study material or references."""
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(300))
    isbn = db.Column(db.String(50))
    publisher = db.Column(db.String(300))
    publish_date = db.Column(db.String(50))
    edition = db.Column(db.String(100))
    notes = db.Column(db.Text)
    pdf_path = db.Column(db.String(1000))
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book_content = db.relationship('BookContent', backref='book', lazy=True, cascade='all, delete-orphan')
    table_of_contents = db.relationship('BookTableOfContents', backref='book', lazy=True, cascade='all, delete-orphan')
    commentaries = db.relationship('Commentary', backref='book', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'isbn': self.isbn,
            'publisher': self.publisher,
            'publish_date': self.publish_date,
            'edition': self.edition,
            'notes': self.notes,
            'pdf_path': self.pdf_path,
            'is_primary': self.is_primary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Pamphlet(db.Model):
    """AA pamphlets and shorter printed materials."""
    __tablename__ = 'pamphlets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    series = db.Column(db.String(50), unique=True, nullable=False)
    publisher = db.Column(db.String(300), nullable=False, default='AA World Services')
    pdf_path = db.Column(db.String(1000))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    content = db.relationship('PamphletContent', backref='pamphlet', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'publisher': self.publisher,
            'series': self.series,
            'pdf_path': self.pdf_path,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class PamphletContent(db.Model):
    """Extracted pamphlet text stored in import order."""
    __tablename__ = 'pamphlet_content'
    id = db.Column(db.Integer, primary_key=True)
    pamphlet_id = db.Column(db.Integer, db.ForeignKey('pamphlets.id'), nullable=False)
    content_mode = db.Column(db.String(20), nullable=False, default='paragraph')
    page = db.Column(db.String(20))
    paragraph = db.Column(db.Integer)
    line = db.Column(db.Integer)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'pamphlet_id': self.pamphlet_id,
            'pamphlet_title': self.pamphlet.title if self.pamphlet else None,
            'series': self.pamphlet.series if self.pamphlet else None,
            'content_mode': self.content_mode,
            'page': self.page,
            'paragraph': self.paragraph,
            'line': self.line,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Dictionary(db.Model):
    """Words and phrases with their meanings."""
    __tablename__ = 'dictionary'
    id = db.Column(db.Integer, primary_key=True)
    word_phrase = db.Column(db.String(500), nullable=False)
    meaning = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    locations = db.relationship('DictionaryLookup', backref='entry', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'word_phrase': self.word_phrase,
            'meaning': self.meaning,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BookLocation(db.Model):
    """A specific location inside a book (chapter/page/paragraph/line)."""
    __tablename__ = 'book_locations'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter = db.Column(db.String(100))
    page = db.Column(db.String(20))       # VARCHAR so roman numerals work
    paragraph = db.Column(db.Integer)
    line_number = db.Column(db.Integer)
    line_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book = db.relationship('Book', backref=db.backref('locations', lazy=True))
    dictionary_lookups = db.relationship('DictionaryLookup', backref='location', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'chapter': self.chapter,
            'page': self.page,
            'paragraph': self.paragraph,
            'line_number': self.line_number,
            'line_text': self.line_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DictionaryLookup(db.Model):
    """Many-to-many bridge: one dictionary entry can appear in many locations."""
    __tablename__ = 'dictionary_lookup'
    id = db.Column(db.Integer, primary_key=True)
    dictionary_id = db.Column(db.Integer, db.ForeignKey('dictionary.id'), nullable=False)
    book_location_id = db.Column(db.Integer, db.ForeignKey('book_locations.id'), nullable=False)
    rank = db.Column(db.Integer)

    def to_dict(self):
        location = self.location
        return {
            'id': self.id,
            'dictionary_id': self.dictionary_id,
            'book_location_id': self.book_location_id,
            'rank': self.rank,
            'word_phrase': self.entry.word_phrase if self.entry else None,
            'meaning': self.entry.meaning if self.entry else None,
            'notes': self.entry.notes if self.entry else None,
            'book_id': location.book_id if location else None,
            'chapter': location.chapter if location else None,
            'page': location.page if location else None,
            'paragraph': location.paragraph if location else None,
            'line_number': location.line_number if location else None,
            'line_text': location.line_text if location else None,
        }


class BookReference(db.Model):
    """Cross-reference between two books."""
    __tablename__ = 'book_references'
    id = db.Column(db.Integer, primary_key=True)
    # Source (the book being read)
    source_book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    source_chapter = db.Column(db.String(100))
    source_page = db.Column(db.String(20))
    source_paragraph = db.Column(db.Integer)
    source_verse = db.Column(db.Integer)
    # Target (the referenced book)
    target_book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    target_chapter = db.Column(db.String(100))
    target_page = db.Column(db.String(20))
    target_paragraph = db.Column(db.Integer)
    target_verse = db.Column(db.Integer)
    # Content
    quoted_text = db.Column(db.Text)
    comments = db.Column(db.Text)
    rank = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source_book = db.relationship('Book', foreign_keys=[source_book_id],
                                  backref=db.backref('outgoing_refs', lazy=True))
    target_book = db.relationship('Book', foreign_keys=[target_book_id],
                                  backref=db.backref('incoming_refs', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'source_book_id': self.source_book_id,
            'source_book_title': self.source_book.title if self.source_book else None,
            'source_chapter': self.source_chapter,
            'source_page': self.source_page,
            'source_paragraph': self.source_paragraph,
            'source_verse': self.source_verse,
            'source_line': self.source_verse,
            'target_book_id': self.target_book_id,
            'target_book_title': self.target_book.title if self.target_book else None,
            'target_chapter': self.target_chapter,
            'target_page': self.target_page,
            'target_paragraph': self.target_paragraph,
            'target_verse': self.target_verse,
            'target_line': self.target_verse,
            'quoted_text': self.quoted_text,
            'comments': self.comments,
            'rank': self.rank,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BookContent(db.Model):
    """Full text contents of a book stored line by line."""
    __tablename__ = 'book_content'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    content_mode = db.Column(db.String(20), nullable=False, default='sentence')
    chapter_number = db.Column(db.String(20))
    chapter_name = db.Column(db.String(100))
    chapter = db.Column(db.String(100))
    page = db.Column(db.String(20))
    paragraph = db.Column(db.Integer)
    line = db.Column(db.Integer)
    verse = db.Column(db.Integer)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    topics = db.relationship('ContentTopic', backref='content', lazy=True,
                             cascade='all, delete-orphan',
                             foreign_keys='ContentTopic.book_content_id')

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'content_mode': self.content_mode,
            'chapter_number': self.chapter_number,
            'chapter_name': self.chapter_name or self.chapter,
            'chapter': self.chapter,
            'page': self.page,
            'paragraph': self.paragraph,
            'line': self.line,
            'verse': self.verse,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BookContentFormat(db.Model):
    """Verse-level presentation formatting for exported/read book text."""
    __tablename__ = 'book_content_formats'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    page = db.Column(db.String(20))
    paragraph = db.Column(db.Integer)
    verse = db.Column(db.Integer)
    is_bold = db.Column(db.Boolean, nullable=False, default=False)
    is_italic = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    book = db.relationship('Book', backref=db.backref('content_formats', lazy=True, cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('book_id', 'page', 'paragraph', 'verse', name='uq_book_content_format_location'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'page': self.page,
            'paragraph': self.paragraph,
            'verse': self.verse,
            'is_bold': self.is_bold,
            'is_italic': self.is_italic,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Topic(db.Model):
    """Topic/tag used to build an index across book content."""
    __tablename__ = 'topics'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    content_links = db.relationship('ContentTopic', backref='topic', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ContentTopic(db.Model):
    """Association between a topic and a book content range."""
    __tablename__ = 'content_topics'
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    book_content_id = db.Column(db.Integer, db.ForeignKey('book_content.id'), nullable=False)
    start_content_id = db.Column(db.Integer, db.ForeignKey('book_content.id'))
    end_content_id = db.Column(db.Integer, db.ForeignKey('book_content.id'))
    notes = db.Column(db.Text)
    rank = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('topic_id', 'book_content_id', name='uq_topic_content'),
    )

    def to_dict(self):
        start_id = self.start_content_id or self.book_content_id
        end_id = self.end_content_id or start_id
        low_id = min(start_id, end_id) if start_id and end_id else start_id
        high_id = max(start_id, end_id) if start_id and end_id else end_id
        content_rows = []
        if low_id and high_id:
            content_rows = (BookContent.query
                            .filter(BookContent.id >= low_id, BookContent.id <= high_id)
                            .order_by(BookContent.id)
                            .all())
        content = content_rows[0] if content_rows else self.content
        combined = _combine_model_content(content_rows) if content_rows else (content.content if content else None)
        return {
            'id': self.id,
            'topic_id': self.topic_id,
            'topic_name': self.topic.name if self.topic else None,
            'book_content_id': self.book_content_id,
            'start_content_id': start_id,
            'end_content_id': end_id,
            'low_content_id': low_id,
            'high_content_id': high_id,
            'book_id': content.book_id if content else None,
            'book_title': content.book.title if content and content.book else None,
            'chapter_number': content.chapter_number if content else None,
            'chapter_name': content.chapter_name if content else None,
            'page': content.page if content else None,
            'paragraph': content.paragraph if content else None,
            'line': content.line if content else None,
            'verse': content.verse if content else None,
            'end_page': content_rows[-1].page if content_rows else (content.page if content else None),
            'end_paragraph': content_rows[-1].paragraph if content_rows else (content.paragraph if content else None),
            'end_line': content_rows[-1].line if content_rows else (content.line if content else None),
            'end_verse': content_rows[-1].verse if content_rows else (content.verse if content else None),
            'content': combined,
            'notes': self.notes,
            'rank': self.rank,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BookTableOfContents(db.Model):
    """Ordered table-of-contents entries for a book."""
    __tablename__ = 'book_table_of_contents'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    chapter_number = db.Column(db.String(20))
    chapter_name = db.Column(db.String(500))
    chapter = db.Column(db.String(100))
    title = db.Column(db.String(500), nullable=False)
    page = db.Column(db.String(20))
    include_by_default = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'sort_order': self.sort_order,
            'chapter_number': self.chapter_number,
            'chapter_name': self.chapter_name or self.title,
            'chapter': self.chapter,
            'title': self.title,
            'page': self.page,
            'include_by_default': self.include_by_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Commentary(db.Model):
    """Personal commentary on a specific location in a book."""
    __tablename__ = 'commentary'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter = db.Column(db.String(100))
    page = db.Column(db.String(20))
    paragraph = db.Column(db.Integer)
    verse = db.Column(db.Integer)
    commentary_text = db.Column(db.Text, nullable=False)
    rank = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'chapter': self.chapter,
            'page': self.page,
            'paragraph': self.paragraph,
            'verse': self.verse,
            'line': self.verse,
            'commentary_text': self.commentary_text,
            'rank': self.rank,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Source(db.Model):
    """Non-book sources: speakers, websites, magazines, etc."""
    __tablename__ = 'sources'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'))
    page = db.Column(db.String(20))
    chapter = db.Column(db.String(100))
    paragraph = db.Column(db.Integer)
    verse = db.Column(db.Integer)
    name = db.Column(db.String(500), nullable=False)
    source_type = db.Column(db.String(100))   # speaker, website, magazine, other
    url = db.Column(db.String(1000))
    author = db.Column(db.String(300))
    publication = db.Column(db.String(500))
    publish_date = db.Column(db.String(50))
    notes = db.Column(db.Text)
    rank = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book = db.relationship('Book', backref=db.backref('sources', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'page': self.page,
            'chapter': self.chapter,
            'paragraph': self.paragraph,
            'verse': self.verse,
            'line': self.verse,
            'name': self.name,
            'source_type': self.source_type,
            'url': self.url,
            'author': self.author,
            'publication': self.publication,
            'publish_date': self.publish_date,
            'notes': self.notes,
            'rank': self.rank,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

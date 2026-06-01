from datetime import datetime
from . import db


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
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    book_content = db.relationship('BookContent', backref='book', lazy=True, cascade='all, delete-orphan')
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
            'is_primary': self.is_primary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Pamphlet(db.Model):
    """Pamphlets and shorter printed materials."""
    __tablename__ = 'pamphlets'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    author = db.Column(db.String(300))
    publisher = db.Column(db.String(300))
    publish_date = db.Column(db.String(50))
    series = db.Column(db.String(300))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'publisher': self.publisher,
            'publish_date': self.publish_date,
            'series': self.series,
            'notes': self.notes,
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

    def to_dict(self):
        return {
            'id': self.id,
            'dictionary_id': self.dictionary_id,
            'book_location_id': self.book_location_id,
            'word_phrase': self.entry.word_phrase if self.entry else None,
            'meaning': self.entry.meaning if self.entry else None,
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
    source_line = db.Column(db.Integer)
    # Target (the referenced book)
    target_book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    target_chapter = db.Column(db.String(100))
    target_page = db.Column(db.String(20))
    target_paragraph = db.Column(db.Integer)
    target_line = db.Column(db.Integer)
    # Content
    quoted_text = db.Column(db.Text)
    comments = db.Column(db.Text)
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
            'source_line': self.source_line,
            'target_book_id': self.target_book_id,
            'target_book_title': self.target_book.title if self.target_book else None,
            'target_chapter': self.target_chapter,
            'target_page': self.target_page,
            'target_paragraph': self.target_paragraph,
            'target_line': self.target_line,
            'quoted_text': self.quoted_text,
            'comments': self.comments,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class BookContent(db.Model):
    """Full text contents of a book stored line by line."""
    __tablename__ = 'book_content'
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    chapter = db.Column(db.String(100))
    page = db.Column(db.String(20))
    paragraph = db.Column(db.Integer)
    line = db.Column(db.Integer)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'book_id': self.book_id,
            'book_title': self.book.title if self.book else None,
            'chapter': self.chapter,
            'page': self.page,
            'paragraph': self.paragraph,
            'line': self.line,
            'content': self.content,
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
    line = db.Column(db.Integer)
    commentary_text = db.Column(db.Text, nullable=False)
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
            'line': self.line,
            'commentary_text': self.commentary_text,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Source(db.Model):
    """Non-book sources: speakers, websites, magazines, etc."""
    __tablename__ = 'sources'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    source_type = db.Column(db.String(100))   # speaker, website, magazine, other
    url = db.Column(db.String(1000))
    author = db.Column(db.String(300))
    publication = db.Column(db.String(500))
    publish_date = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'source_type': self.source_type,
            'url': self.url,
            'author': self.author,
            'publication': self.publication,
            'publish_date': self.publish_date,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

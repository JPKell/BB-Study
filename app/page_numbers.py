from sqlalchemy import text


def roman_to_int(value):
    """Return an integer for a roman numeral page label, or None."""
    text = str(value or '').strip().lower()
    if not text:
        return None
    roman_values = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
    if any(char not in roman_values for char in text):
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        value = roman_values[char]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total or None


def page_label_sort_key(page):
    page = str(page or '')
    if page.startswith('front-'):
        return (0, page)
    roman = roman_to_int(page)
    if roman is not None:
        return (1, roman)
    if page.isdigit():
        return (2, int(page))
    return (3, page)


def calculate_relative_page_numbers(page_labels):
    """Map stored page labels to physical relative page numbers.

    Roman page labels use their roman value. Numeric page labels start after the
    roman front matter, skipping one physical page when needed so page 1 is odd.
    """
    labels = sorted({str(page) for page in page_labels if page is not None and str(page) != ''}, key=page_label_sort_key)
    roman_labels = [label for label in labels if roman_to_int(label) is not None]
    numeric_labels = [label for label in labels if str(label).isdigit()]
    other_labels = [label for label in labels if label not in roman_labels and label not in numeric_labels]

    mapping = {label: roman_to_int(label) for label in roman_labels}
    last_roman = max(mapping.values(), default=0)
    numeric_offset = last_roman
    if numeric_offset % 2:
        numeric_offset += 1

    for label in numeric_labels:
        mapping[label] = numeric_offset + int(label)

    next_relative = max(mapping.values(), default=0) + 1
    for label in other_labels:
        mapping[label] = next_relative
        next_relative += 1
    return mapping


def populate_book_relative_page_numbers(book_id=None):
    from . import db
    from .models import Book, BookContent

    book_ids = [book_id] if book_id else [row[0] for row in db.session.query(Book.id).all()]
    for current_book_id in book_ids:
        pages = [
            row[0]
            for row in db.session.query(BookContent.page)
            .filter(BookContent.book_id == current_book_id)
            .distinct()
            .all()
            if row[0] is not None
        ]
        mapping = calculate_relative_page_numbers(pages)
        for page, relative in mapping.items():
            db.session.execute(
                text('UPDATE book_content SET relative_page_number = :relative WHERE book_id = :book_id AND page = :page'),
                {'relative': relative, 'book_id': current_book_id, 'page': page},
            )
    db.session.commit()


def relative_page_for_label(book_id, page):
    from .models import BookContent

    row = (
        BookContent.query
        .filter_by(book_id=book_id, page=str(page))
        .filter(BookContent.relative_page_number.isnot(None))
        .order_by(BookContent.id)
        .first()
    )
    return row.relative_page_number if row else None


def page_label_for_relative(book_id, relative_page_number):
    from .models import BookContent

    row = (
        BookContent.query
        .filter_by(book_id=book_id, relative_page_number=relative_page_number)
        .order_by(BookContent.id)
        .first()
    )
    return str(row.page) if row else None

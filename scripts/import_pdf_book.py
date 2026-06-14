#!/usr/bin/env python3
"""Extract a book PDF into review text files and optionally import it."""
import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PDF_ROOT = ROOT / 'app' / 'pdf'

ROMAN_RE = re.compile(r'^(?=[ivxlcdm]+$)[ivxlcdm]+$', re.IGNORECASE)
PAGE_RE = re.compile(r'^\d+$')
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"\'(])')
WORD_RE = re.compile(r'\b[A-Za-z]{2,}\b')
NON_BREAKING_ABBREVIATIONS = ('A.A.', 'Dr.', 'Mr.', 'Ms.', 'Mrs.')
ABBREVIATION_TOKEN = '<DOT>'
KNOWN_TITLES = {
    'preface': 'Preface',
    'foreword to first edition': 'Foreword to First Edition',
    'foreword': 'Foreword',
    "the doctor's opinion": "The Doctor's Opinion",
    "bill's story": "Bill's Story",
    'there is a solution': 'There Is a Solution',
    'more about alcoholism': 'More About Alcoholism',
    'we agnostics': 'We Agnostics',
    'how it works': 'How It Works',
    'into action': 'Into Action',
    'working with others': 'Working with Others',
    'to wives': 'To Wives',
    'the family afterward': 'The Family Afterward',
    'to employers': 'To Employers',
    'a vision for you': 'A Vision for You',
}
OCR_FIXES = {
    'ANO NYMO US': 'ANONYMOUS',
    'A nonymous': 'Anonymous',
    'A.A .': 'A.A.',
    'ALCO HOLICS': 'ALCOHOLICS',
    'Becaus e': 'Because',
    'Capta in': 'Captain',
    'Chapte r': 'Chapter',
    'DO CTOR': 'DOCTOR',
    'GENE RAL': 'GENERAL',
    'Fore word': 'Foreword',
    'Forewo rd': 'Foreword',
    'H ow': 'How',
    'H e': 'He',
    'MO ST': 'MOST',
    'N o': 'No',
    'O F': 'OF',
    'O ne': 'One',
    'O ur': 'Our',
    'P. O.': 'P.O.',
    'T his': 'This',
    'T hough': 'Though',
    'Trea tment': 'Treatment',
    'Tw elve': 'Twelve',
    'U S': 'US',
    'W E': 'WE',
    'W e': 'We',
    'YOR K': 'YORK',
    'a nd': 'and',
    'a vocation': 'avocation',
    'a lcoholic': 'alcoholic',
    'a lcoholics': 'alcoholics',
    'a ll': 'all',
    'a re': 'are',
    'acc ounts': 'accounts',
    'acc urate': 'accurate',
    'ad dres sed': 'addressed',
    'alco hol': 'alcohol',
    'alco holic': 'alcoholic',
    'alcoho lic': 'alcoholic',
    'appea l': 'appeal',
    'appea ls': 'appeals',
    'appea r': 'appear',
    'appea ranc e': 'appearance',
    'ap peal': 'appeal',
    'ba sic': 'basic',
    'b ecame': 'became',
    'b elieve': 'believe',
    'be en': 'been',
    'bec ause': 'because',
    'bec ame': 'became',
    'bec ome': 'become',
    'bod y': 'body',
    'c annot': 'cannot',
    'c lear': 'clear',
    'c onvic tions': 'convictions',
    'c onvincing': 'convincing',
    'c ould': 'could',
    'ca n': 'can',
    'clea r': 'clear',
    'com menced': 'commenced',
    'com mon': 'common',
    'comprehe nd': 'comprehend',
    'conside r': 'consider',
    'd esc ribes': 'describes',
    'd ifficult': 'difficult',
    'd ues': 'dues',
    'de sire': 'desire',
    'des ire': 'desire',
    'des ignating': 'designating',
    'diseas e': 'disease',
    'd rinking': 'drinking',
    'doc tor': 'doctor',
    'docto r': 'doctor',
    'e leme nt': 'element',
    'e nough': 'enough',
    'e ssential': 'essential',
    'e very': 'every',
    'eac h': 'each',
    'exa mple': 'example',
    'exp eriences': 'experiences',
    'faile d': 'failed',
    'favo rably': 'favorably',
    'fell ': 'felt ',
    'form ': 'from ',
    'ge tting': 'getting',
    'ha d': 'had',
    'ha s': 'has',
    'he lp': 'help',
    'himse lf': 'himself',
    'ho pe': 'hope',
    'hosp ital': 'hospital',
    'hum an': 'human',
    'ide als': 'ideals',
    'in- nermost': 'innermost',
    'ine vitab ly': 'inevitably',
    'injurio us': 'injurious',
    'irritable ': 'irritable ',
    'leve l': 'level',
    'lis tene d': 'listened',
    'ma de': 'made',
    'maxi- mum': 'maximum',
    'me dical': 'medical',
    'me et': 'meet',
    'me mbers': 'members',
    'me n': 'men',
    'membe rship': 'membership',
    'moveme nt': 'movement',
    'ne ares t': 'nearest',
    'ne ver': 'never',
    'orde r': 'order',
    'ordinary ': 'ordinary ',
    'ove rwhelm': 'overwhelm',
    'pa ramount': 'paramount',
    'p aramount': 'paramount',
    'pe ople': 'people',
    'pe rsonal': 'personal',
    'perso n': 'person',
    'p henomenon': 'phenomenon',
    'p roblem': 'problem',
    'p roposa ls': 'proposals',
    'p ursue': 'pursue',
    'psychic ': 'psychic ',
    'rec overed': 'recovered',
    'rec overy': 'recovery',
    'reflec tion': 'reflection',
    'representatio n': 'representation',
    'reso lution': 'resolution',
    's ee': 'see',
    's eem': 'seem',
    's eemed': 'seemed',
    's eldom': 'seldom',
    's ense': 'sense',
    's entiment': 'sentiment',
    's hall': 'shall',
    's hip': 'ship',
    's o': 'so',
    's olved': 'solved',
    's pecial': 'special',
    's pree': 'spree',
    's tage': 'stage',
    's uccumbed': 'succumbed',
    'se lves': 'selves',
    'se ntiment': 'sentiment',
    'se parated': 'separated',
    'se paration': 'separation',
    'se nse': 'sense',
    'se nsation': 'sensation',
    'se nt': 'sent',
    'self-centerednes s': 'self-centeredness',
    'sentimenta l': 'sentimental',
    'so cial': 'social',
    'so metimes': 'sometimes',
    'somew hat': 'somewhat',
    'subside ': 'subside ',
    'the m': 'them',
    'the y': 'they',
    'tow ard': 'toward',
    'to ward': 'toward',
    'un- common': 'uncommon',
    'un- touched': 'untouched',
    'w as': 'was',
    'w e': 'we',
    'w ell': 'well',
    'w hich': 'which',
    'w hile': 'while',
    'w ho': 'who',
    'w ill': 'will',
    'w ith': 'with',
    'w ives': 'wives',
    'w omen': 'women',
    'wo uld': 'would',
}
DICTIONARY_WORDS = None


@dataclass
class TocEntry:
    sort_order: int
    chapter_number: str
    chapter: str
    title: str
    page: str
    include_by_default: bool = True


@dataclass
class ContentLine:
    content_mode: str
    chapter_number: str
    chapter: str
    page: str
    paragraph: int
    line: int
    verse: int
    content: str


def run_command(args):
    try:
        return subprocess.run(args, check=True, text=True, capture_output=True).stdout
    except FileNotFoundError:
        sys.exit(f'Missing required command: {args[0]}')
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.stderr.strip() or f'Command failed: {" ".join(args)}')


def page_count(pdf_path):
    info = run_command(['pdfinfo', str(pdf_path)])
    for row in info.splitlines():
        if row.startswith('Pages:'):
            return int(row.split(':', 1)[1].strip())
    raise RuntimeError('Could not read page count from pdfinfo output')


def extract_pdf_pages(pdf_path):
    count = page_count(pdf_path)
    pages = []
    for page_num in range(1, count + 1):
        text = run_command([
            'pdftotext', '-layout', '-f', str(page_num), '-l', str(page_num),
            str(pdf_path), '-'
        ])
        pages.append(text.replace('\f', '').rstrip())
    return pages


def dictionary_words():
    global DICTIONARY_WORDS
    if DICTIONARY_WORDS is not None:
        return DICTIONARY_WORDS
    words = set()
    for path in (Path('/usr/share/dict/words'), Path('/usr/share/dict/american-english')):
        if path.exists():
            for raw in path.read_text(errors='ignore').splitlines():
                word = raw.strip().lower()
                if word.isalpha() and len(word) > 2:
                    words.add(word)
    words.update({
        'alcoholics', 'anonymous', 'alcoholism', 'camaraderie', 'selfishness',
        'self-centeredness', 'grapevine', 'silkworth', 'appendices',
        'we', 'he', 'of', 'as', 'to', 'is', 'it', 'in', 'on', 'or', 'be', 'by',
        'my', 'me', 'us', 'up', 'no',
    })
    DICTIONARY_WORDS = words
    return words


def preserve_case(original, merged):
    if original.isupper():
        return merged.upper()
    if original[:1].isupper():
        return merged.capitalize()
    return merged


def repair_split_words(text):
    words = dictionary_words()
    pattern = re.compile(r'\b([A-Za-z]{1,7}) ([A-Za-z]{1,})\b')
    changed = True
    while changed:
        changed = False

        def replace(match):
            nonlocal changed
            left, right = match.groups()
            if left.islower() and right[:1].isupper():
                return match.group(0)
            if right.lower() in {'a', 'an', 'and', 'as', 'at', 'by', 'for', 'from', 'in', 'of', 'on', 'one', 'or', 'the', 'to', 'us', 'with'}:
                return match.group(0)
            merged = left + right
            if len(left) == 1:
                short_words = {'we', 'he', 'of', 'as', 'to', 'is', 'it', 'in', 'on', 'or', 'be', 'by', 'my', 'me', 'us', 'up', 'no'}
                if merged.lower() not in short_words and (left.lower() in {'a', 'i'} or len(merged) < 4):
                    return match.group(0)
            if merged.lower() in words:
                changed = True
                return preserve_case(left + right, merged)
            return match.group(0)

        text = pattern.sub(replace, text)
    return text


def clean_ocr_spacing(text, strip=True):
    text = text.replace('—', '--').replace('“', '"').replace('”', '"').replace('’', "'")
    text = re.sub(r'(?<=\w)-\s+(?=\w)', '', text)
    for bad, good in sorted(OCR_FIXES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.match(r'^[A-Za-z] [A-Za-z]{1,2}$', bad):
            continue
        text = text.replace(bad, good)
    text = repair_split_words(text)
    text = re.sub(r"('s)(?=[A-Za-z])", r"\1 ", text)
    text = text.replace('themoment', 'the moment')
    text = text.replace('Captain\'s table', "Captain's table")
    text = text.replace("ship's pas sengers", "ship's passengers")
    text = text.replace('bac kgro unds', 'backgrounds')
    text = text.replace('vesse l', 'vessel')
    text = text.replace('escap e', 'escape')
    text = text.replace('disaste r', 'disaster')
    text = text.replace('no t', 'not')
    text = text.replace('eve ry', 'every')
    text = text.replace('powe rful', 'powerful')
    text = text.replace('tremend ous', 'tremendous')
    text = text.replace('seeme d', 'seemed')
    text = text.replace('showe d', 'showed')
    text = text.replace('req uests', 'requests')
    text = text.replace('Creato r', 'Creator')
    text = text.replace('e ver', 'ever')
    text = text.replace('H ow', 'How')
    text = text.replace(' w as ', ' was ')
    text = text.replace('ha ve', 'have')
    text = text.replace('ruthless ly', 'ruthlessly')
    text = text.replace(' o f ', ' of ')
    text = text.replace(' a nd ', ' and ')
    text = text.replace(' a s ', ' as ')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip() if strip else text.rstrip()


def normalized_title(text):
    text = clean_ocr_spacing(text)
    text = re.sub(r'[^A-Za-z0-9\' ]+', '', text).lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return KNOWN_TITLES.get(text, text.title())


def extract_toc(pages):
    entries = []
    order = 1
    front_entries = [
        TocEntry(order, '', 'Title Page', 'Title Page', 'front-001', False),
        TocEntry(order + 1, '', 'Contents', 'Contents', 'front-002', False),
    ]
    entries.extend(front_entries)
    order += len(front_entries)

    is_service_manual = any('THE A.A. SERVICE MANUAL' in page for page in pages[:4])
    is_twelve_and_twelve = any('THE TWELVE STEPS' in page for page in pages[:4])
    toc_pages = 20 if is_service_manual else 12 if is_twelve_and_twelve else 4
    toc_text = '\n'.join(pages[:toc_pages])
    for raw in toc_text.splitlines():
        line = clean_ocr_spacing(raw)
        line = re.sub(r'\.{2,}', ' ', line)
        line = re.sub(r'\s+', ' ', line).strip()
        if is_twelve_and_twelve:
            twelve_match = re.match(
                r'^(FOREWORD|STEP\s+\w+|TRADITION\s+\w+)\s+(\d+)$',
                line,
                re.IGNORECASE,
            )
            if twelve_match:
                title = twelve_match.group(1).title()
                page = twelve_match.group(2)
                entries.append(TocEntry(order, '', title, title, page))
                order += 1
            continue
        service_match = re.match(
            r'^(CHAPTER\s+(\d+)|APPENDICES|APPENDIX\s+([A-Z])|MAPS|CONCEPT\s+([IVXLCDM]+)|FOREWORD|INTRODUCTION|GLOSSARY OF GENERAL SERVICE TERMS|GENERAL SERVICE TERMS|INDEX)(?:\s+(.+?))?\s+([A-Z]-[IVXLCDM]+|[ivxlcdm]+|\d+)$',
            line,
            re.IGNORECASE,
        )
        if service_match:
            label = service_match.group(1)
            if label.upper() == 'GENERAL SERVICE TERMS':
                label = 'GLOSSARY OF GENERAL SERVICE TERMS'
            chapter_number = service_match.group(2) or service_match.group(3) or service_match.group(4) or ''
            title = ' '.join(part for part in (label, service_match.group(5) or '') if part)
            title = re.sub(r'\s+', ' ', title).strip().title()
            title = title.replace("'S", "'s").replace('Aa Grapevine', 'AA Grapevine')
            page = service_match.group(6)
            entries.append(TocEntry(order, chapter_number, label.title(), title, page))
            order += 1
            continue
        match = re.match(r'^(?:(\d+)\s+)?(.+?)\s+([ivxlcdm]+|\d+)$', line, re.IGNORECASE)
        if not match:
            continue
        chapter_number, title, page = match.groups()
        title = normalized_title(title)
        if title.lower() in {'chapter', 'page', 'contents'}:
            continue
        if toc_pages > 4 and not chapter_number and title.lower() not in {
            'foreword',
            'introduction welcome to general service',
            'glossary of general service terms',
            'index',
        }:
            continue
        entries.append(TocEntry(order, chapter_number or '', chapter_number or '', title, page))
        order += 1
    return dedupe_toc(entries)


def dedupe_toc(entries):
    seen = set()
    unique = []
    for entry in entries:
        key = (entry.title.lower(), entry.page)
        if key in seen:
            continue
        seen.add(key)
        entry.sort_order = len(unique) + 1
        unique.append(entry)
    return unique


def page_sort_key(page):
    roman = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}
    if str(page).isdigit():
        return 10000 + int(page)
    total = prev = 0
    for char in reversed(str(page).lower()):
        value = roman.get(char, 0)
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def infer_printed_page(lines, physical_page):
    nonempty = [clean_ocr_spacing(line) for line in lines if line.strip()]
    if not nonempty:
        return f'front-{physical_page:03d}'
    if physical_page == 1:
        return 'front-001'
    if physical_page == 2 and 'contents' in nonempty[0].lower():
        return 'front-002'
    first_tokens = nonempty[0].split()
    last_tokens = nonempty[-1].split()
    candidates = []
    first_is_chapter_label = re.match(r'^chapter\s+\d+$', nonempty[0], re.IGNORECASE)
    if first_tokens and not first_is_chapter_label:
        candidates.append(first_tokens[-1])
    if last_tokens:
        candidates.append(last_tokens[-1])
    if first_tokens and not first_is_chapter_label:
        candidates.append(first_tokens[0])
    if last_tokens:
        candidates.append(last_tokens[0])
    for token in candidates:
        token = token.strip()
        if PAGE_RE.match(token) or ROMAN_RE.match(token):
            return token.lower()
    return f'front-{physical_page:03d}'


def chapter_for_page(page, toc_entries):
    if str(page).startswith('front-'):
        return '', 'Title Page' if page == 'front-001' else 'Contents'
    candidates = [entry for entry in toc_entries if not str(entry.page).startswith('front-')]
    current = None
    page_key = page_sort_key(page)
    for entry in sorted(candidates, key=lambda item: page_sort_key(item.page)):
        if page_sort_key(entry.page) <= page_key:
            current = entry
        else:
            break
    return (current.chapter_number, current.title) if current else ('', 'Front Matter')


def strip_running_headers(lines, printed_page, chapter):
    cleaned = list(lines)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    if not cleaned:
        return cleaned

    first = clean_ocr_spacing(cleaned[0])
    last = clean_ocr_spacing(cleaned[-1])
    first_parts = first.split()
    if first_parts and (first_parts[0].lower() == str(printed_page).lower() or first_parts[-1].lower() == str(printed_page).lower()):
        cleaned.pop(0)
    if cleaned and clean_ocr_spacing(cleaned[-1]).lower() == str(printed_page).lower():
        cleaned.pop()
    elif cleaned and re.match(
        r'^' + re.escape(str(printed_page)) + r'\s+THE A\.A\. SERVICE MANUAL$',
        clean_ocr_spacing(cleaned[-1]),
        re.IGNORECASE,
    ):
        cleaned.pop()
    elif cleaned and last.endswith(f' {printed_page}'):
        cleaned[-1] = re.sub(r'\s+' + re.escape(str(printed_page)) + r'$', '', cleaned[-1]).rstrip()

    chapter_text = clean_ocr_spacing(chapter).lower()
    chapter_without_number = re.sub(r'^chapter\s+\d+\s+', '', chapter_text)
    filtered = []
    for index, line in enumerate(cleaned):
        text = clean_ocr_spacing(line)
        lowered = text.lower()
        leading_spaces = len(line) - len(line.lstrip(' '))
        is_edge = index == 0 or index == len(cleaned) - 1
        if lowered.startswith('table of conten'):
            continue
        if chapter_text and lowered == chapter_text and (is_edge or leading_spaces > 24):
            continue
        if chapter_without_number and lowered == chapter_without_number:
            continue
        if text == 'AAWS' and leading_spaces > 24:
            continue
        filtered.append(line)
    cleaned = filtered

    chapter_words = set(re.findall(r'[a-z]+', chapter.lower()))
    if cleaned:
        maybe_header = set(re.findall(r'[a-z]+', clean_ocr_spacing(cleaned[0]).lower()))
        if chapter_words and maybe_header and maybe_header <= chapter_words:
            cleaned.pop(0)
    return cleaned


def protect_sentence_abbreviations(text):
    for abbreviation in NON_BREAKING_ABBREVIATIONS:
        protected = abbreviation.replace('.', ABBREVIATION_TOKEN)
        text = re.sub(re.escape(abbreviation), protected, text, flags=re.IGNORECASE)
    return text


def restore_sentence_abbreviations(text):
    return text.replace(ABBREVIATION_TOKEN, '.')


def split_sentences(text):
    text = clean_ocr_spacing(text)
    if not text:
        return []
    protected = protect_sentence_abbreviations(text)
    return [
        restore_sentence_abbreviations(part.strip())
        for part in SENTENCE_RE.split(protected)
        if part.strip()
    ]


def repair_wrapped_line_words(lines):
    cleaned = [clean_ocr_spacing(line) if line.strip() else '' for line in lines]
    for index in range(len(cleaned) - 1):
        current = cleaned[index]
        following = cleaned[index + 1]
        if not current.endswith('-') or not following:
            continue
        match = re.match(r'^([A-Za-z]+)(\b.*)$', following)
        if not match:
            continue
        fragment, rest = match.groups()
        cleaned[index] = current[:-1] + fragment
        cleaned[index + 1] = rest.lstrip()
    return cleaned


def paragraph_blocks(lines):
    paragraphs = []
    current = []
    for line in lines:
        if not line:
            if current:
                paragraphs.append(current)
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(current)
    return paragraphs


def split_line_fragments(line):
    protected_line = protect_sentence_abbreviations(line)
    parts = []
    start = 0
    for match in re.finditer(r'[.!?](?=\s+["A-Z]|\s*$)', protected_line):
        end = match.end()
        fragment = restore_sentence_abbreviations(protected_line[start:end].strip())
        if fragment:
            parts.append((fragment, True))
        start = end
    tail = restore_sentence_abbreviations(protected_line[start:].strip())
    if tail:
        parts.append((tail, False))
    return parts or [(line, False)]


def parse_page(raw_text, physical_page, toc_entries):
    raw_lines = raw_text.splitlines()
    printed_page = infer_printed_page(raw_lines, physical_page)
    chapter_number, chapter = chapter_for_page(printed_page, toc_entries)
    body_lines = strip_running_headers(raw_lines, printed_page, chapter)
    literal_paragraphs = paragraph_blocks([
        clean_ocr_spacing(line) if line.strip() else ''
        for line in body_lines
    ])

    content_rows = []
    line_counter = 1
    for paragraph_index, paragraph_lines in enumerate(literal_paragraphs, start=1):
        verse_number = 1
        active_verse = verse_number
        for line in paragraph_lines:
            for fragment, ends_sentence in split_line_fragments(line):
                content_rows.append(ContentLine(
                    'fragment', chapter_number, chapter, printed_page,
                    paragraph_index, line_counter, active_verse, fragment
                ))
                if ends_sentence:
                    verse_number += 1
                    active_verse = verse_number
            line_counter += 1
    return printed_page, chapter_number, chapter, content_rows


def safe_name(value):
    value = re.sub(r'[^A-Za-z0-9._-]+', '-', value).strip('-')
    return value or 'untitled'


def write_review_files(pdf_path, parsed_pages):
    output_dir = pdf_path.with_suffix('')
    output_dir.mkdir(exist_ok=True)
    fragment_dir = output_dir / 'fragments'
    fragment_dir.mkdir(exist_ok=True)
    for old_file in fragment_dir.glob('*.txt'):
        old_file.unlink()
    for stale_dir_name in ('sentence', 'line'):
        stale_dir = output_dir / stale_dir_name
        if stale_dir.exists():
            for old_file in stale_dir.glob('*.txt'):
                old_file.unlink()

    seen = set()
    for physical_page, (printed_page, chapter_number, chapter, content_rows) in enumerate(parsed_pages, start=1):
        chapter_label = f'{chapter_number}-{chapter}' if chapter_number else chapter
        base_filename = f'{safe_name(chapter_label)}.{safe_name(printed_page)}'
        filename = f'{base_filename}.txt'
        if filename in seen:
            filename = f'{base_filename}.physical-{physical_page:03d}.txt'
        seen.add(filename)
        with (fragment_dir / filename).open('w', encoding='utf-8') as handle:
            for row in content_rows:
                handle.write(f'p{row.paragraph}.v{row.verse}\t{row.content}\n')
    return output_dir


def import_to_database(args, toc_entries, content_lines):
    sys.path.insert(0, str(ROOT))
    from app import create_app, db
    from app.models import Book, BookContent, BookTableOfContents

    app = create_app()
    with app.app_context():
        book = None
        if args.book_id:
            book = Book.query.get(args.book_id)
        if not book:
            book = Book.query.filter_by(title=args.title).first()
        if not book:
            book = Book(title=args.title)
            db.session.add(book)

        book.author = args.author
        book.publisher = args.publisher
        book.publish_date = args.publish_date
        book.edition = args.edition
        book.pdf_path = str(args.pdf.relative_to(APP_PDF_ROOT))

        if args.replace:
            BookContent.query.filter_by(book_id=book.id).delete()
            BookTableOfContents.query.filter_by(book_id=book.id).delete()
            db.session.flush()

        for entry in toc_entries:
            db.session.add(BookTableOfContents(
                book=book,
                sort_order=entry.sort_order,
                chapter_number=entry.chapter_number,
                chapter_name=entry.title,
                chapter=entry.chapter,
                title=entry.title,
                page=entry.page,
                include_by_default=entry.include_by_default,
            ))

        for line in content_lines:
            db.session.add(BookContent(
                book=book,
                content_mode=line.content_mode,
                chapter_number=line.chapter_number,
                chapter_name=line.chapter,
                chapter=line.chapter,
                page=line.page,
                paragraph=line.paragraph,
                verse=line.verse,
                content=line.content,
            ))
        db.session.commit()
        return book.id


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path, help='PDF path under app/pdf')
    parser.add_argument('--title', default='Alcoholics Anonymous', help='Book title to create/update')
    parser.add_argument('--author', default='Alcoholics Anonymous World Services, Inc.')
    parser.add_argument('--publisher', default='Alcoholics Anonymous World Services, Inc.')
    parser.add_argument('--publish-date', default='1955')
    parser.add_argument('--edition', default='Second Edition')
    parser.add_argument('--book-id', type=int, help='Existing book id to update')
    parser.add_argument('--import-db', action='store_true', help='Write extracted content to the database')
    parser.add_argument('--replace', action='store_true', help='Replace existing content and TOC for the book')
    return parser.parse_args()


def main():
    args = parse_args()
    args.pdf = args.pdf.resolve()
    if not args.pdf.is_file():
        sys.exit(f'PDF not found: {args.pdf}')
    if APP_PDF_ROOT.resolve() not in args.pdf.parents:
        sys.exit(f'PDF must be inside {APP_PDF_ROOT}')

    pages = extract_pdf_pages(args.pdf)
    toc_entries = extract_toc(pages)
    parsed_pages = [parse_page(page, index + 1, toc_entries) for index, page in enumerate(pages)]
    output_dir = write_review_files(args.pdf, parsed_pages)
    content_lines = [
        line
        for _, _, _, content_rows in parsed_pages
        for line in content_rows
    ]

    print(f'Wrote {len(parsed_pages)} page review files to {output_dir}')
    print(f'Extracted {len(content_lines)} content rows and {len(toc_entries)} TOC entries')
    if args.import_db:
        book_id = import_to_database(args, toc_entries, content_lines)
        print(f'Imported into book id {book_id}')
    else:
        print('Database unchanged; rerun with --import-db to import rows')


if __name__ == '__main__':
    main()

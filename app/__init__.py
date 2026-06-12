import os
import click
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)

    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'study.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'bb-study-secret-key-change-in-production'

    db.init_app(app)

    from .routes.main import main_bp
    from .routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()
        _sync_sqlite_schema()
        _seed_settings()

    @app.cli.command('import-pamphlets')
    @click.argument('filepath')
    def import_pamphlets_cmd(filepath):
        """Import pamphlets from a JSON extraction file into the database."""
        from app.services.pamphlet_importer import import_pamphlet_json
        import logging
        logging.basicConfig(level=logging.INFO, format='%(message)s')

        click.echo(f"Importing pamphlets from: {filepath}")
        result = import_pamphlet_json(filepath)
        click.echo(
            f"\nImport complete:\n"
            f"  Pamphlets imported : {result['pamphlets']}\n"
            f"  Pages imported     : {result['pages']}\n"
            f"  Content rows       : {result['rows']}\n"
            f"  Errors             : {result['errors']}"
        )

    return app


def _sync_sqlite_schema():
    """Keep the local SQLite database compatible with lightweight model changes."""
    inspector = inspect(db.engine)
    book_columns = {col['name'] for col in inspector.get_columns('books')}
    if 'pdf_path' not in book_columns:
        db.session.execute(text('ALTER TABLE books ADD COLUMN pdf_path VARCHAR(1000)'))
        db.session.commit()
    content_columns = {col['name'] for col in inspector.get_columns('book_content')}
    if 'content_mode' not in content_columns:
        db.session.execute(text("ALTER TABLE book_content ADD COLUMN content_mode VARCHAR(20) NOT NULL DEFAULT 'sentence'"))
        db.session.commit()
    if 'chapter_number' not in content_columns:
        db.session.execute(text('ALTER TABLE book_content ADD COLUMN chapter_number VARCHAR(20)'))
        db.session.commit()
    if 'chapter_name' not in content_columns:
        db.session.execute(text('ALTER TABLE book_content ADD COLUMN chapter_name VARCHAR(100)'))
        db.session.execute(text('UPDATE book_content SET chapter_name = chapter WHERE chapter_name IS NULL'))
        db.session.commit()
    if 'verse' not in content_columns:
        db.session.execute(text('ALTER TABLE book_content ADD COLUMN verse INTEGER'))
        db.session.execute(text('UPDATE book_content SET verse = line WHERE verse IS NULL'))
        db.session.commit()
    if 'relative_page_number' not in content_columns:
        db.session.execute(text('ALTER TABLE book_content ADD COLUMN relative_page_number INTEGER'))
        db.session.commit()

    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS book_content_formats ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'book_id INTEGER NOT NULL, '
        'page VARCHAR(20), '
        'paragraph INTEGER, '
        'verse INTEGER, '
        'is_bold BOOLEAN NOT NULL DEFAULT 0, '
        'is_italic BOOLEAN NOT NULL DEFAULT 0, '
        "content_role VARCHAR(30) NOT NULL DEFAULT 'body', "
        'alignment_override VARCHAR(20), '
        'created_at DATETIME, '
        'updated_at DATETIME, '
        'FOREIGN KEY(book_id) REFERENCES books(id), '
        'CONSTRAINT uq_book_content_format_location UNIQUE (book_id, page, paragraph, verse)'
        ')'
    ))
    db.session.commit()
    format_columns = {col['name'] for col in inspector.get_columns('book_content_formats')}
    if 'content_role' not in format_columns:
        db.session.execute(text("ALTER TABLE book_content_formats ADD COLUMN content_role VARCHAR(30) NOT NULL DEFAULT 'body'"))
        db.session.commit()
    if 'alignment_override' not in format_columns:
        db.session.execute(text('ALTER TABLE book_content_formats ADD COLUMN alignment_override VARCHAR(20)'))
        db.session.commit()
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS book_page_formats ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'book_id INTEGER NOT NULL, '
        'page VARCHAR(20) NOT NULL, '
        'centered_export BOOLEAN NOT NULL DEFAULT 0, '
        'created_at DATETIME, '
        'updated_at DATETIME, '
        'FOREIGN KEY(book_id) REFERENCES books(id), '
        'CONSTRAINT uq_book_page_format_location UNIQUE (book_id, page)'
        ')'
    ))
    db.session.commit()
    toc_columns = {col['name'] for col in inspector.get_columns('book_table_of_contents')}
    if 'chapter_number' not in toc_columns:
        db.session.execute(text('ALTER TABLE book_table_of_contents ADD COLUMN chapter_number VARCHAR(20)'))
        db.session.commit()
    if 'chapter_name' not in toc_columns:
        db.session.execute(text('ALTER TABLE book_table_of_contents ADD COLUMN chapter_name VARCHAR(500)'))
        db.session.execute(text('UPDATE book_table_of_contents SET chapter_name = title WHERE chapter_name IS NULL'))
        db.session.commit()
    pamphlet_columns = {col['name'] for col in inspector.get_columns('pamphlets')}
    if 'pdf_path' not in pamphlet_columns:
        db.session.execute(text('ALTER TABLE pamphlets ADD COLUMN pdf_path VARCHAR(1000)'))
        db.session.commit()
    if 'publisher' in pamphlet_columns:
        db.session.execute(text(
            "UPDATE pamphlets SET publisher = 'AA World Services' "
            "WHERE publisher IS NULL OR publisher = ''"
        ))
        db.session.commit()
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_pamphlets_series_unique ON pamphlets(series)'))
    db.session.commit()
    content_topic_columns = {col['name'] for col in inspector.get_columns('content_topics')}
    if 'start_content_id' not in content_topic_columns:
        db.session.execute(text('ALTER TABLE content_topics ADD COLUMN start_content_id INTEGER'))
        db.session.execute(text('UPDATE content_topics SET start_content_id = book_content_id WHERE start_content_id IS NULL'))
        db.session.commit()
    if 'end_content_id' not in content_topic_columns:
        db.session.execute(text('ALTER TABLE content_topics ADD COLUMN end_content_id INTEGER'))
        db.session.execute(text('UPDATE content_topics SET end_content_id = book_content_id WHERE end_content_id IS NULL'))
        db.session.commit()
    if 'rank' not in content_topic_columns:
        db.session.execute(text('ALTER TABLE content_topics ADD COLUMN rank INTEGER'))
        db.session.commit()
    source_columns = {col['name'] for col in inspector.get_columns('sources')}
    source_schema_updates = {
        'book_id': 'INTEGER',
        'page': 'VARCHAR(20)',
        'chapter': 'VARCHAR(100)',
        'paragraph': 'INTEGER',
        'line': 'INTEGER',
        'verse': 'INTEGER',
    }
    for column, column_type in source_schema_updates.items():
        if column not in source_columns:
            db.session.execute(text(f'ALTER TABLE sources ADD COLUMN {column} {column_type}'))
            db.session.commit()
    if 'rank' not in source_columns:
        db.session.execute(text('ALTER TABLE sources ADD COLUMN rank INTEGER'))
        db.session.commit()
    if 'verse' in source_columns or 'line' in source_columns:
        db.session.execute(text('UPDATE sources SET verse = line WHERE verse IS NULL AND line IS NOT NULL'))
        db.session.commit()
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS source_urls ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'source_id INTEGER NOT NULL, '
        'url VARCHAR(1000) NOT NULL, '
        'label VARCHAR(300), '
        'sort_order INTEGER NOT NULL DEFAULT 0, '
        'created_at DATETIME, '
        'FOREIGN KEY(source_id) REFERENCES sources(id)'
        ')'
    ))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_source_urls_source_id ON source_urls(source_id)'))
    db.session.execute(text(
        'INSERT INTO source_urls (source_id, url, sort_order, created_at) '
        'SELECT s.id, s.url, 0, s.created_at FROM sources s '
        'WHERE s.url IS NOT NULL AND s.url != "" '
        'AND NOT EXISTS ('
        'SELECT 1 FROM source_urls su WHERE su.source_id = s.id AND su.url = s.url'
        ')'
    ))
    db.session.commit()

    commentary_columns = {col['name'] for col in inspector.get_columns('commentary')}
    if 'verse' not in commentary_columns:
        db.session.execute(text('ALTER TABLE commentary ADD COLUMN verse INTEGER'))
        db.session.execute(text('UPDATE commentary SET verse = line WHERE verse IS NULL AND line IS NOT NULL'))
        db.session.commit()
    if 'rank' not in commentary_columns:
        db.session.execute(text('ALTER TABLE commentary ADD COLUMN rank INTEGER'))
        db.session.commit()
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS reflect_prompts ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'book_id INTEGER NOT NULL, '
        'chapter VARCHAR(100), '
        'page VARCHAR(20), '
        'paragraph INTEGER, '
        'verse INTEGER, '
        'prompt_text TEXT NOT NULL, '
        'rank INTEGER, '
        'created_at DATETIME, '
        'updated_at DATETIME, '
        'FOREIGN KEY(book_id) REFERENCES books(id)'
        ')'
    ))
    db.session.commit()

    reference_columns = {col['name'] for col in inspector.get_columns('book_references')}
    if 'source_verse' not in reference_columns:
        db.session.execute(text('ALTER TABLE book_references ADD COLUMN source_verse INTEGER'))
        db.session.execute(text('UPDATE book_references SET source_verse = source_line WHERE source_verse IS NULL AND source_line IS NOT NULL'))
        db.session.commit()
    if 'target_verse' not in reference_columns:
        db.session.execute(text('ALTER TABLE book_references ADD COLUMN target_verse INTEGER'))
        db.session.execute(text('UPDATE book_references SET target_verse = target_line WHERE target_verse IS NULL AND target_line IS NOT NULL'))
        db.session.commit()
    if 'rank' not in reference_columns:
        db.session.execute(text('ALTER TABLE book_references ADD COLUMN rank INTEGER'))
        db.session.commit()

    dictionary_lookup_columns = {col['name'] for col in inspector.get_columns('dictionary_lookup')}
    if 'rank' not in dictionary_lookup_columns:
        db.session.execute(text('ALTER TABLE dictionary_lookup ADD COLUMN rank INTEGER'))
        db.session.commit()


def _seed_settings():
    from .models import Setting
    if not Setting.query.filter_by(key='theme').first():
        db.session.add(Setting(key='theme', value='dark'))
        db.session.commit()
    if not Setting.query.filter_by(key='current_book_id').first():
        db.session.add(Setting(key='current_book_id', value=''))
        db.session.commit()
    if not Setting.query.filter_by(key='current_secondary_book_id').first():
        db.session.add(Setting(key='current_secondary_book_id', value=''))
        db.session.commit()
    if not Setting.query.filter_by(key='current_page').first():
        db.session.add(Setting(key='current_page', value='1'))
        db.session.commit()
    if not Setting.query.filter_by(key='current_content_mode').first():
        db.session.add(Setting(key='current_content_mode', value='sentence'))
        db.session.commit()
    if not Setting.query.filter_by(key='export_text_layout').first():
        db.session.add(Setting(key='export_text_layout', value='reflow_justified'))
        db.session.commit()
    export_defaults = {
        'export_page_size': 'letter',
        'export_book_alignment': 'justify',
        'export_definition_alignment': 'left',
        'export_definition_header_alignment': 'left',
        'export_reflect_alignment': 'left',
        'export_reflect_header_alignment': 'left',
        'export_commentary_alignment': 'left',
        'export_annotation_alignment': 'left',
        'export_title_alignment': 'center',
        'export_subtitle_alignment': 'center',
        'export_content_chapter_alignment': 'center',
        'export_header_alignment': 'left',
        'export_title_font_size': '14',
        'export_subtitle_font_size': '12',
        'export_content_chapter_font_size': '12',
        'export_header_font_size': '10.5',
        'export_title_bold': '1',
        'export_title_italic': '0',
        'export_subtitle_bold': '0',
        'export_subtitle_italic': '1',
        'export_content_chapter_bold': '1',
        'export_content_chapter_italic': '0',
        'export_header_bold': '1',
        'export_header_italic': '0',
        'export_definition_bold': '0',
        'export_definition_italic': '0',
        'export_definition_all_caps': '0',
        'export_definition_header_bold': '1',
        'export_definition_header_italic': '0',
        'export_definition_header_all_caps': '0',
        'export_reflect_bold': '0',
        'export_reflect_italic': '0',
        'export_reflect_all_caps': '0',
        'export_reflect_header_bold': '1',
        'export_reflect_header_italic': '0',
        'export_reflect_header_all_caps': '0',
        'export_title_line_spacing': '1.2',
        'export_subtitle_line_spacing': '1.2',
        'export_content_chapter_line_spacing': '1.2',
        'export_header_line_spacing': '1.2',
        'export_title_margin_above': '0',
        'export_title_margin_below': '0',
        'export_subtitle_margin_above': '0',
        'export_subtitle_margin_below': '0',
        'export_content_chapter_margin_above': '0',
        'export_content_chapter_margin_below': '0',
        'export_header_margin_above': '0',
        'export_header_margin_below': '0',
        'export_definition_margin_above': '0',
        'export_definition_margin_below': '0',
        'export_title_kerning': '0',
        'export_subtitle_kerning': '0',
        'export_content_chapter_kerning': '0',
        'export_header_kerning': '0',
        'export_title_font': 'Times-Roman',
        'export_subtitle_font': 'Times-Roman',
        'export_content_chapter_font': 'Helvetica',
        'export_header_font': 'Helvetica',
        'export_title_gray': '0',
        'export_subtitle_gray': '15',
        'export_content_chapter_gray': '0',
        'export_header_gray': '20',
        'export_chapter_bold': '0',
        'export_chapter_italic': '0',
        'export_page_number_bold': '0',
        'export_page_number_italic': '0',
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
        'export_definition_header_font_size': '8.3',
        'export_reflect_font_size': '8.3',
        'export_reflect_header_font_size': '8.3',
        'export_commentary_font_size': '7',
        'export_annotation_font_size': '9',
        'export_inline_marker_font_size': '7.2',
        'export_footnote_marker_font_size': '6.2',
        'export_chapter_line_spacing': '1.0',
        'export_page_number_line_spacing': '1.0',
        'export_book_line_spacing': '1.35',
        'export_definition_line_spacing': '1.3',
        'export_definition_header_line_spacing': '1.3',
        'export_reflect_line_spacing': '1.3',
        'export_reflect_header_line_spacing': '1.3',
        'export_commentary_line_spacing': '1.28',
        'export_annotation_line_spacing': '1.33',
        'export_chapter_kerning': '0',
        'export_page_number_kerning': '0',
        'export_book_kerning': '0',
        'export_definition_kerning': '0',
        'export_definition_header_kerning': '0',
        'export_reflect_kerning': '0',
        'export_reflect_header_kerning': '0',
        'export_commentary_kerning': '0',
        'export_annotation_kerning': '0',
        'export_inline_marker_kerning': '0',
        'export_footnote_marker_kerning': '0',
        'export_chapter_font': 'Helvetica',
        'export_page_number_font': 'Helvetica',
        'export_book_font': 'Times-Roman',
        'export_definition_font': 'Helvetica',
        'export_definition_header_font': 'Helvetica',
        'export_reflect_font': 'Helvetica',
        'export_reflect_header_font': 'Helvetica',
        'export_commentary_font': 'Helvetica',
        'export_annotation_font': 'Helvetica',
        'export_inline_marker_font': 'Helvetica',
        'export_footnote_marker_font': 'Helvetica',
        'export_chapter_gray': '30',
        'export_page_number_gray': '40',
        'export_book_gray': '0',
        'export_definition_gray': '0',
        'export_definition_header_gray': '0',
        'export_reflect_gray': '0',
        'export_reflect_header_gray': '0',
        'export_commentary_gray': '0',
        'export_annotation_gray': '0',
        'export_inline_marker_gray': '0',
        'export_footnote_marker_gray': '0',
        'export_inline_marker_raise': '4',
        'export_footnote_marker_raise': '4',
        'export_inline_marker_bold': '1',
        'export_inline_marker_italic': '0',
        'export_footnote_marker_bold': '1',
        'export_footnote_marker_italic': '0',
        'export_reflect_margin_above': '0',
        'export_reflect_margin_below': '0',
    }
    for key, value in export_defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))
    db.session.commit()

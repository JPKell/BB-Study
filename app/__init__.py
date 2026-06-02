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
    source_columns = {col['name'] for col in inspector.get_columns('sources')}
    source_schema_updates = {
        'book_id': 'INTEGER',
        'page': 'VARCHAR(20)',
        'chapter': 'VARCHAR(100)',
        'paragraph': 'INTEGER',
        'line': 'INTEGER',
    }
    for column, column_type in source_schema_updates.items():
        if column not in source_columns:
            db.session.execute(text(f'ALTER TABLE sources ADD COLUMN {column} {column_type}'))
            db.session.commit()


def _seed_settings():
    from .models import Setting
    if not Setting.query.filter_by(key='theme').first():
        db.session.add(Setting(key='theme', value='dark'))
        db.session.commit()
    if not Setting.query.filter_by(key='current_book_id').first():
        db.session.add(Setting(key='current_book_id', value=''))
        db.session.commit()
    if not Setting.query.filter_by(key='current_page').first():
        db.session.add(Setting(key='current_page', value='1'))
        db.session.commit()
    if not Setting.query.filter_by(key='current_content_mode').first():
        db.session.add(Setting(key='current_content_mode', value='sentence'))
        db.session.commit()

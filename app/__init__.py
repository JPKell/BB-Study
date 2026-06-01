import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

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
        _seed_settings()

    return app


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

import pytest
from flask import Flask
from sqlalchemy import text

from app import _sync_sqlite_schema, db
from app.routes.api import api_bp


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config['TESTING'] = True
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(application)
    application.register_blueprint(api_bp, url_prefix='/api')
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def test_topics_endpoint_survives_blank_created_at_after_schema_sync(app):
    with app.app_context():
        db.session.execute(
            text("INSERT INTO topics (name, description, created_at) VALUES ('amends', '', '')")
        )
        db.session.commit()

        _sync_sqlite_schema()

        response = app.test_client().get('/api/topics')

        assert response.status_code == 200
        assert response.get_json() == [
            {
                'id': 1,
                'name': 'amends',
                'description': '',
                'created_at': None,
            }
        ]

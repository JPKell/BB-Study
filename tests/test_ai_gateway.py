import json
from pathlib import Path

import pytest
from flask import Flask

from app import db
from app.models import Setting
from app.routes.api import api_bp
from app.services import ai_gateway


@pytest.fixture
def app():
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        REPOSITORY_ROOT=str(Path(__file__).resolve().parents[1]),
    )
    db.init_app(application)
    application.register_blueprint(api_bp, url_prefix='/api')
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


def test_ai_settings_never_return_api_key(app):
    client = app.test_client()
    response = client.put('/api/ai/settings', json={
        'gateway_address': 'http://localhost:1234/v1/',
        'api_key': 'secret-value',
        'system_prompt': 'Review my prose.',
    })

    assert response.status_code == 200
    assert response.get_json()['data']['api_key_configured'] is True
    assert 'secret-value' not in response.get_data(as_text=True)
    assert 'ai_api_key' not in client.get('/api/settings').get_json()
    db_rows = client.get('/api/db/tables/settings?per_page=200').get_json()['rows']
    secret_row = next(row for row in db_rows if row['key'] == 'ai_api_key')
    assert secret_row['value'] == '••••••••'
    assert client.get('/api/ai/settings').get_json() == {
        'gateway_address': 'http://localhost:1234/v1',
        'system_prompt': 'Review my prose.',
        'selected_model': '',
        'api_key_configured': True,
    }


def test_models_and_chat_use_saved_gateway_settings(app, monkeypatch):
    calls = {}

    def fake_models(address, api_key):
        calls['models'] = (address, api_key)
        return ['model-a', 'model-b']

    def fake_chat(address, api_key, model, messages, system_prompt):
        calls['chat'] = (address, api_key, model, messages, system_prompt)
        return 'A useful response.'

    monkeypatch.setattr(ai_gateway, 'list_models', fake_models)
    monkeypatch.setattr(ai_gateway, 'chat', fake_chat)
    with app.app_context():
        db.session.add_all([
            Setting(key='ai_gateway_address', value='https://ai.example/v1'),
            Setting(key='ai_api_key', value='test-key'),
            Setting(key='ai_system_prompt', value='Be concise.'),
        ])
        db.session.commit()

    client = app.test_client()
    models_response = client.get('/api/ai/models')
    chat_response = client.post('/api/ai/chat', json={
        'model': 'model-b',
        'messages': [{'role': 'user', 'content': 'Review this.'}],
    })

    assert models_response.get_json()['models'] == ['model-a', 'model-b']
    assert calls['models'] == ('https://ai.example/v1', 'test-key')
    assert chat_response.get_json()['message']['content'] == 'A useful response.'
    assert calls['chat'] == (
        'https://ai.example/v1',
        'test-key',
        'model-b',
        [{'role': 'user', 'content': 'Review this.'}],
        'Be concise.',
    )


def test_gateway_client_builds_openai_compatible_chat_request(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                'choices': [{'message': {'content': 'Looks good.'}}],
            }).encode()

    def fake_urlopen(request, timeout):
        captured['url'] = request.full_url
        captured['authorization'] = request.headers['Authorization']
        captured['payload'] = json.loads(request.data)
        captured['timeout'] = timeout
        return Response()

    monkeypatch.setattr(ai_gateway, 'urlopen', fake_urlopen)
    result = ai_gateway.chat(
        'https://ai.example/v1',
        'abc123',
        'writer-model',
        [{'role': 'user', 'content': 'Help.'}],
        'You are an editor.',
    )

    assert result == 'Looks good.'
    assert captured['url'] == 'https://ai.example/v1/chat/completions'
    assert captured['authorization'] == 'Bearer abc123'
    assert captured['payload']['messages'][0] == {
        'role': 'system', 'content': 'You are an editor.',
    }

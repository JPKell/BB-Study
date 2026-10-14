"""Small OpenAI-compatible HTTP client used by the reader's AI panel."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class AIGatewayError(RuntimeError):
    """Raised when an AI gateway cannot be reached or returns invalid data."""


def _endpoint(gateway_address, resource):
    address = (gateway_address or '').strip().rstrip('/')
    parsed = urlparse(address)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise AIGatewayError('Gateway address must be a valid http:// or https:// URL.')
    return f'{address}/{resource.lstrip("/")}'


def _headers(api_key):
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    return headers


def _request_json(url, api_key, method='GET', payload=None, timeout=45):
    body = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(url, data=body, headers=_headers(api_key), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(5 * 1024 * 1024 + 1)
    except HTTPError as exc:
        detail = ''
        try:
            error_data = json.loads(exc.read().decode('utf-8'))
            detail = error_data.get('error', {}).get('message') or error_data.get('error') or ''
        except (ValueError, AttributeError, UnicodeDecodeError):
            pass
        message = f'Gateway returned HTTP {exc.code}'
        raise AIGatewayError(f'{message}: {detail}' if detail else message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, 'reason', None) or str(exc)
        raise AIGatewayError(f'Could not connect to the AI gateway: {reason}') from exc

    if len(raw) > 5 * 1024 * 1024:
        raise AIGatewayError('Gateway response was too large.')
    try:
        return json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AIGatewayError('Gateway returned an invalid JSON response.') from exc


def list_models(gateway_address, api_key):
    """Return sorted model IDs from an OpenAI-compatible gateway."""
    data = _request_json(_endpoint(gateway_address, 'models'), api_key, timeout=15)
    rows = data.get('data', data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise AIGatewayError('Gateway model response did not contain a model list.')
    models = []
    for row in rows:
        model_id = row.get('id') if isinstance(row, dict) else row
        if model_id and str(model_id) not in models:
            models.append(str(model_id))
    return sorted(models, key=str.casefold)


def chat(gateway_address, api_key, model, messages, system_prompt=''):
    """Send a conversation and return the first assistant response as text."""
    outbound_messages = []
    if system_prompt:
        outbound_messages.append({'role': 'system', 'content': system_prompt})
    outbound_messages.extend(messages)
    data = _request_json(
        _endpoint(gateway_address, 'chat/completions'),
        api_key,
        method='POST',
        payload={'model': model, 'messages': outbound_messages},
    )
    try:
        content = data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise AIGatewayError('Gateway response did not contain an assistant message.') from exc
    if isinstance(content, list):
        content = ''.join(
            part.get('text', '') for part in content
            if isinstance(part, dict) and part.get('type') in {None, 'text'}
        )
    if not isinstance(content, str):
        raise AIGatewayError('Gateway returned an unsupported assistant message format.')
    return content

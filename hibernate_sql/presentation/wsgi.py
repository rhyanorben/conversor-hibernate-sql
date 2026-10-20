import json
from email.message import Message
from http import HTTPStatus

from hibernate_sql.application.conversion import ConversionService
from hibernate_sql.presentation.http import (
    RequestError, convert_response, get_response, read_payload,
)


def make_application(service: ConversionService):
    def application(environ, start_response):
        method = environ.get('REQUEST_METHOD', 'GET')
        path = environ.get('PATH_INFO', '/')
        content_type = 'application/json; charset=utf-8'
        extra_headers = []

        if method in ('GET', 'HEAD'):
            status, body, content_type = get_response(service, path)
        elif method == 'POST':
            if path != '/convert':
                status, body = 404, {'error': 'Página não encontrada.'}
            else:
                headers = Message()
                for key, name in (
                    ('CONTENT_LENGTH', 'Content-Length'),
                    ('CONTENT_TYPE', 'Content-Type'),
                    ('HTTP_TRANSFER_ENCODING', 'Transfer-Encoding'),
                ):
                    if key in environ:
                        headers[name] = environ[key]
                try:
                    payload = read_payload(headers, environ['wsgi.input'])
                    body = convert_response(service, payload)
                    status = 200
                except RequestError as error:
                    status, body = error.status, {'error': str(error)}
                except ValueError as error:
                    status, body = 400, {'error': str(error)}
                except TimeoutError:
                    status, body = 408, {'error': 'Tempo limite para receber os logs excedido.'}
        else:
            status, body = 405, {'error': 'Método não permitido.'}
            extra_headers = [('Allow', 'GET, HEAD, POST')]

        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        start_response(f'{status} {HTTPStatus(status).phrase}', [
            ('Content-Type', content_type),
            ('Content-Length', str(len(data))),
            ('Cache-Control', 'no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ] + extra_headers)
        return [data] if method != 'HEAD' else []

    return application

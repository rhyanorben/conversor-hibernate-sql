import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Type
from urllib.parse import urlsplit

from hibernate_sql.application.conversion import ConversionService


WEB_DIRECTORY = Path(__file__).with_name('web')
MAX_BODY_BYTES = 5_000_000
REQUEST_TIMEOUT_SECONDS = 10
STATIC_ROUTES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/controller.js': ('controller.js', 'text/javascript; charset=utf-8'),
    '/api.js': ('api.js', 'text/javascript; charset=utf-8'),
}


class RequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class ConversionHandler(BaseHTTPRequestHandler):
    service: ConversionService

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def reply(self, status: int, body, content_type: str = 'application/json; charset=utf-8') -> None:
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in STATIC_ROUTES:
            filename, content_type = STATIC_ROUTES[path]
            try:
                body = (WEB_DIRECTORY / filename).read_bytes()
            except OSError:
                self.reply(503, {'error': 'Interface indisponível.'})
                return
            self.reply(200, body, content_type)
        elif path == '/prefixes':
            self.reply(200, list(self.service.prefixes))
        else:
            self.reply(404, {'error': 'Página não encontrada.'})

    def read_payload(self) -> dict:
        if self.headers.get('Transfer-Encoding'):
            raise RequestError('Transfer-Encoding não é suportado.')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise RequestError('Content-Length inválido.')
        length = int(lengths[0])
        if length == 0:
            raise RequestError('Informe um corpo JSON.')
        if length > MAX_BODY_BYTES:
            raise RequestError('Cole no máximo 5 MB de logs.', 413)
        if self.headers.get_content_type() != 'application/json':
            raise RequestError('Use Content-Type application/json.', 415)
        body = self.rfile.read(length)
        if len(body) != length:
            raise RequestError('Corpo da requisição incompleto.')
        try:
            payload = json.loads(body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise RequestError('JSON inválido. Envie um objeto em UTF-8.') from None
        if not isinstance(payload, dict) or not isinstance(payload.get('log'), str):
            raise RequestError('Informe os logs como texto.')
        return payload

    def do_POST(self) -> None:
        if urlsplit(self.path).path != '/convert':
            self.reply(404, {'error': 'Página não encontrada.'})
            return
        try:
            payload = self.read_payload()
            result = self.service.execute(payload['log'], payload.get('prefix', ''))
        except RequestError as error:
            self.reply(error.status, {'error': str(error)})
        except ValueError as error:
            self.reply(400, {'error': str(error)})
        except TimeoutError:
            self.reply(408, {'error': 'Tempo limite para receber os logs excedido.'})
        else:
            self.reply(200, {'sql': result.sql, 'count': result.count})


def make_handler(service: ConversionService) -> Type[ConversionHandler]:
    class ConfiguredHandler(ConversionHandler):
        pass

    ConfiguredHandler.service = service
    return ConfiguredHandler

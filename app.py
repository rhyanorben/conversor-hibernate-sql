"""Interface local, sem pacotes externos. Execute: python3 app.py."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

from converter import convert

# Adicione novas opções aqui; a interface carrega esta lista automaticamente.
PREFIXES = {'EXPLAIN ANALYZE': 'EXPLAIN ANALYZE'}
PAGE = Path(__file__).with_name('index.html')


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/':
            self.reply(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/prefixes':
            self.reply(200, list(PREFIXES))
        else:
            self.reply(404, {'error': 'Página não encontrada.'})

    def do_POST(self):
        if self.path != '/convert':
            self.reply(404, {'error': 'Página não encontrada.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 5_000_000:
                raise ValueError('Cole no máximo 5 MB de logs.')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or not isinstance(payload.get('log'), str):
                raise ValueError('Informe os logs como texto.')
            prefix_name = payload.get('prefix', '')
            if not isinstance(prefix_name, str) or prefix_name and prefix_name not in PREFIXES:
                raise ValueError('Prefixo inválido.')
            queries = convert(payload['log'])
            prefix = PREFIXES.get(prefix_name, '')
            output = '\n\n'.join((prefix + '\n' if prefix else '') + sql.rstrip().rstrip(';') + '\n;' for sql in queries)
            self.reply(200, {'sql': output, 'count': len(queries)})
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            self.reply(400, {'error': str(error)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Conversor de logs Hibernate para PostgreSQL')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        url = f'http://127.0.0.1:{server.server_port}'
        print(f'Hibernate SQL: {url}\nCtrl+C para encerrar.', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

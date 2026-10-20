import argparse
import webbrowser
from http.server import ThreadingHTTPServer
from typing import Optional, Sequence

from hibernate_sql.application.conversion import ConversionService
from hibernate_sql.infrastructure.hibernate_logs import HibernateLogParser
from hibernate_sql.presentation.http import make_handler
from hibernate_sql.presentation.wsgi import make_application


service = ConversionService(HibernateLogParser())
Handler = make_handler(service)
application = make_application(service)


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('A porta deve ser um número entre 0 e 65535.') from None
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError('A porta deve estar entre 0 e 65535.')
    return port


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description='Conversor de logs Hibernate para PostgreSQL')
    parser.add_argument('--port', type=port_number, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
        url = f'http://127.0.0.1:{server.server_port}'
        print(f'Hibernate SQL: {url}\nCtrl+C para encerrar.', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

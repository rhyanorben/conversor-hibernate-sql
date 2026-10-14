import io
import json
import threading
import unittest
from email.message import Message
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from app import Handler
from hibernate_sql.presentation.http import (
    ConversionHandler, MAX_BODY_BYTES, RequestError, STATIC_ROUTES,
)


class HttpIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def test_all_static_routes_and_response_headers(self):
        for path, (_, content_type) in STATIC_ROUTES.items():
            with self.subTest(path=path):
                status, headers, body = self.request('GET', path + '?v=1')
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], content_type)
                self.assertEqual(int(headers['Content-Length']), len(body))
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertTrue(body)

    def test_prefixes_and_unknown_routes(self):
        status, _, body = self.request('GET', '/prefixes')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), ['EXPLAIN ANALYZE'])
        for method, path in [('GET', '/missing'), ('GET', '/../app.py'), ('POST', '/missing')]:
            with self.subTest(method=method, path=path):
                status, _, body = self.request(method, path)
                self.assertEqual(status, 404)
                self.assertIn('error', json.loads(body))

    def test_conversion_with_and_without_prefix(self):
        cases = [('', 'select 42\n;'), ('EXPLAIN ANALYZE', 'EXPLAIN ANALYZE\nselect 42\n;')]
        for prefix, expected in cases:
            with self.subTest(prefix=prefix):
                payload = {
                    'log': 'Hibernate: select ?\nbinding parameter (1:INT) <- [42]',
                    'prefix': prefix,
                }
                status, _, body = self.request(
                    'POST', '/convert', json.dumps(payload),
                    {'Content-Type': 'application/json; charset=utf-8'},
                )
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {'sql': expected, 'count': 1})

    def test_invalid_payloads_and_conversion_errors(self):
        payloads = [
            [], None, {}, {'log': 1}, {'log': ''}, {'log': 'select ?'},
            {'log': 'select 1', 'prefix': []}, {'log': 'select 1', 'prefix': 'unknown'},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                status, _, body = self.request(
                    'POST', '/convert', json.dumps(payload), {'Content-Type': 'application/json'},
                )
                self.assertEqual(status, 400)
                self.assertIn('error', json.loads(body))

    def test_invalid_json_and_utf8(self):
        for body in [b'{', b'\xff', b'[' * 2000]:
            with self.subTest(body=body[:10]):
                status, _, response = self.request(
                    'POST', '/convert', body, {'Content-Type': 'application/json'},
                )
                self.assertEqual(status, 400)
                self.assertIn('JSON inválido', json.loads(response)['error'])

    def test_invalid_lengths_media_type_and_transfer_encoding(self):
        cases = [
            ({'Content-Length': 'invalid'}, 400),
            ({'Content-Length': '-1'}, 400),
            ({'Content-Length': '0'}, 400),
            ({'Content-Length': str(MAX_BODY_BYTES + 1)}, 413),
            ({'Content-Type': 'text/plain'}, 415),
            ({'Transfer-Encoding': 'chunked'}, 400),
        ]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                status, _, response = self.request('POST', '/convert', '{}', headers)
                self.assertEqual(status, expected)
                self.assertIn('error', json.loads(response))

    def test_missing_static_file(self):
        with patch('hibernate_sql.presentation.http.Path.read_bytes', side_effect=OSError):
            status, _, body = self.request('GET', '/')
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {'error': 'Interface indisponível.'})


class RequestValidationTests(unittest.TestCase):
    def make_handler(self, lengths, body=b'{}'):
        handler = object.__new__(ConversionHandler)
        handler.headers = Message()
        for length in lengths:
            handler.headers.add_header('Content-Length', length)
        handler.headers.add_header('Content-Type', 'application/json')
        handler.rfile = io.BytesIO(body)
        return handler

    def test_missing_duplicate_non_ascii_and_truncated_lengths(self):
        cases = [
            ([], 'Content-Length'), (['2', '2'], 'Content-Length'),
            (['²'], 'Content-Length'), (['10'], 'incompleto'),
        ]
        for lengths, expected in cases:
            with self.subTest(lengths=lengths), self.assertRaisesRegex(RequestError, expected):
                self.make_handler(lengths).read_payload()

    def test_maximum_body_length_is_accepted(self):
        body = b'{"log":"select 1"}'
        body += b' ' * (MAX_BODY_BYTES - len(body))
        payload = self.make_handler([str(MAX_BODY_BYTES)], body).read_payload()
        self.assertEqual(payload, {'log': 'select 1'})

    def test_timeout_response(self):
        handler = self.make_handler(['2'])
        handler.path = '/convert'
        handler.rfile = Mock()
        handler.rfile.read.side_effect = TimeoutError
        handler.reply = Mock()
        handler.do_POST()
        handler.reply.assert_called_once_with(
            408, {'error': 'Tempo limite para receber os logs excedido.'},
        )

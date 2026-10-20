import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator

from app import application
from hibernate_sql.presentation.http import MAX_BODY_BYTES, STATIC_ROUTES


class RecordingInput(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class WsgiIntegrationTests(unittest.TestCase):
    def request(self, method, path, body=b'', overrides=None, stream=None, validate=True):
        environ = {}
        setup_testing_defaults(environ)
        url = urlsplit(path)
        environ.update({
            'REQUEST_METHOD': method,
            'PATH_INFO': url.path,
            'QUERY_STRING': url.query,
            'CONTENT_TYPE': 'application/json; charset=utf-8',
            'CONTENT_LENGTH': str(len(body)),
            'wsgi.input': stream if stream is not None else io.BytesIO(body),
        })
        for key, value in (overrides or {}).items():
            if value is None:
                environ.pop(key, None)
            else:
                environ[key] = value
        response = {}
        written = []

        def start_response(status, headers, exc_info=None):
            response['status'] = int(status.split(' ', 1)[0])
            response['headers'] = dict(headers)
            self.assertEqual(len(headers), len(response['headers']))
            return written.append

        app = validator(application) if validate else application
        result = app(environ, start_response)
        try:
            chunks = list(result)
        finally:
            if hasattr(result, 'close'):
                result.close()
        data = b''.join(written + chunks)
        headers = response['headers']
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        if method == 'HEAD':
            self.assertEqual(data, b'')
        else:
            self.assertEqual(int(headers['Content-Length']), len(data))
        return response['status'], headers, data

    def assert_error(self, status, body, expected_status, message=None):
        self.assertEqual(status, expected_status)
        error = json.loads(body)
        self.assertIsInstance(error['error'], str)
        if message is not None:
            self.assertIn(message, error['error'])

    def test_static_routes_and_headers_follow_wsgi_contract(self):
        for path, (_, content_type) in STATIC_ROUTES.items():
            with self.subTest(path=path):
                status, headers, body = self.request('GET', path + '?v=cloud')
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], content_type)
                self.assertTrue(body)

    def test_prefixes_and_conversion_ignore_query_string(self):
        status, headers, body = self.request('GET', '/prefixes?source=cloud')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')
        self.assertEqual(json.loads(body), ['EXPLAIN ANALYZE'])
        log = 'Hibernate: select ?\nbinding parameter (1:VARCHAR) <- [João]'
        for prefix in ['', 'EXPLAIN ANALYZE']:
            with self.subTest(prefix=prefix):
                payload = json.dumps({'log': log, 'prefix': prefix}, ensure_ascii=False).encode('utf-8')
                stream = RecordingInput(payload + b'not part of the request')
                status, _, body = self.request('POST', '/convert?source=cloud', payload, stream=stream)
                self.assertEqual(status, 200)
                sql = (prefix + '\n' if prefix else '') + "select E'João'\n;"
                self.assertEqual(json.loads(body), {'sql': sql, 'count': 1})
                self.assertEqual(stream.read_sizes, [len(payload)])

    def test_head_preserves_get_headers_without_sending_body(self):
        for path in ['/', '/prefixes?source=cloud', '/missing']:
            with self.subTest(path=path):
                get_status, get_headers, _ = self.request('GET', path)
                status, headers, _ = self.request('HEAD', path)
                self.assertEqual(status, get_status)
                self.assertEqual(headers, get_headers)

    def test_interleaved_threads_are_converted_through_the_public_api(self):
        log = '\n'.join([
            '2026-10-20T10:00:00 DEBUG [one] org.hibernate.SQL : select ?',
            '2026-10-20T10:00:00 DEBUG [two] org.hibernate.SQL : select ?',
            '2026-10-20T10:00:00 TRACE [two] org.hibernate.orm.jdbc.bind : binding parameter (1:INT) <- [2]',
            '2026-10-20T10:00:00 TRACE [one] org.hibernate.orm.jdbc.bind : binding parameter (1:INT) <- [1]',
        ])
        payload = json.dumps({'log': log}).encode('utf-8')
        status, _, body = self.request('POST', '/convert', payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'sql': 'select 1\n;\n\nselect 2\n;', 'count': 2})

    def test_conversion_errors_expose_query_thread_parameter_and_line_to_the_browser(self):
        log = '\n'.join([
            'Hibernate: select 1',
            '2026-10-20T10:00:00 DEBUG [worker-2] org.hibernate.SQL : select ?',
            '2026-10-20T10:00:00 TRACE [worker-2] org.hibernate.orm.jdbc.bind : binding parameter (1:BOOLEAN) <- [yes]',
        ])
        payload = json.dumps({'log': log}).encode('utf-8')
        status, _, body = self.request('POST', '/convert', payload)
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body), {
            'error': 'Query 2, SQL na linha 2, thread worker-2, parâmetro 1, linha 3: Booleano inválido: yes',
        })

    def test_missing_routes_and_unsupported_methods(self):
        for method, path in [('GET', '/missing'), ('GET', '/../app.py'), ('POST', '/missing')]:
            with self.subTest(method=method, path=path):
                status, _, body = self.request(method, path)
                self.assert_error(status, body, 404)
        for method, path in [('PUT', '/'), ('DELETE', '/convert'), ('OPTIONS', '/prefixes')]:
            with self.subTest(method=method, path=path):
                status, _, body = self.request(method, path)
                self.assert_error(status, body, 405)

    def test_invalid_json_and_utf8(self):
        for payload in [b'{', b'\xff', b'[' * 2000]:
            with self.subTest(payload=payload[:10]):
                status, _, body = self.request('POST', '/convert', payload)
                self.assert_error(status, body, 400, 'JSON inválido')

    def test_invalid_payloads_and_conversion_errors(self):
        for payload in [[], None, {}, {'log': 1}, {'log': ''}, {'log': 'select ?'},
                        {'log': 'select 1', 'prefix': []}, {'log': 'select 1', 'prefix': 'unknown'}]:
            with self.subTest(payload=payload):
                data = json.dumps(payload).encode('utf-8')
                status, _, body = self.request('POST', '/convert', data)
                self.assert_error(status, body, 400)

    def test_missing_invalid_and_zero_lengths_do_not_read_input(self):
        for length in [None, '', 'invalid', '-1', '1.5', '²', '2,2', '0']:
            with self.subTest(length=length):
                stream = RecordingInput(b'{}')
                # The WSGI validator rejects malformed lengths before invoking the app.
                status, _, body = self.request(
                    'POST', '/convert', b'{}', {'CONTENT_LENGTH': length}, stream, validate=False,
                )
                self.assert_error(status, body, 400)
                self.assertEqual(stream.read_sizes, [])

    def test_rejects_oversized_body_without_reading_it(self):
        for length, validate in [(str(MAX_BODY_BYTES + 1), True), ('9' * 5000, False)]:
            with self.subTest(digits=len(length)):
                stream = RecordingInput(b'{}')
                status, _, body = self.request(
                    'POST', '/convert', b'{}', {'CONTENT_LENGTH': length}, stream, validate=validate,
                )
                self.assert_error(status, body, 413, '5 MB')
                self.assertEqual(stream.read_sizes, [])

    def test_maximum_body_length_is_accepted(self):
        payload = b'{"log":"select 1"}'
        payload += b' ' * (MAX_BODY_BYTES - len(payload))
        status, _, body = self.request('POST', '/convert', payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'sql': 'select 1\n;', 'count': 1})

    def test_unsupported_content_type_and_transfer_encoding_do_not_read_input(self):
        cases = [
            ({'CONTENT_TYPE': None}, 415),
            ({'CONTENT_TYPE': 'text/plain'}, 415),
            ({'HTTP_TRANSFER_ENCODING': 'chunked'}, 400),
        ]
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                stream = RecordingInput(b'{}')
                status, _, body = self.request('POST', '/convert', b'{}', overrides, stream)
                self.assert_error(status, body, expected)
                self.assertEqual(stream.read_sizes, [])

    def test_truncated_body_and_timeout(self):
        status, _, body = self.request('POST', '/convert', b'{}', {'CONTENT_LENGTH': '10'})
        self.assert_error(status, body, 400, 'incompleto')
        stream = io.BytesIO(b'{}')
        stream.read = Mock(side_effect=TimeoutError)
        status, _, body = self.request('POST', '/convert', b'{}', stream=stream)
        self.assert_error(status, body, 408, 'Tempo limite')

    def test_missing_static_file_returns_json_service_unavailable(self):
        with patch('pathlib.Path.read_bytes', side_effect=OSError):
            status, headers, body = self.request('GET', '/')
        self.assert_error(status, body, 503, 'Interface indisponível.')
        self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')

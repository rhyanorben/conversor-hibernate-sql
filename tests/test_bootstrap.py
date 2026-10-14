import argparse
import io
import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from hibernate_sql.bootstrap import Handler, main, port_number


class BootstrapTests(unittest.TestCase):
    def test_compatibility_entry_point_calls_main(self):
        with patch('hibernate_sql.bootstrap.main') as start:
            runpy.run_path('app.py', run_name='__main__')
        start.assert_called_once_with()

    def test_valid_and_invalid_ports(self):
        for value in ['0', '8765', '65535']:
            self.assertEqual(port_number(value), int(value))
        for value in ['-1', '65536', 'abc']:
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                port_number(value)

    def test_server_starts_and_closes_on_keyboard_interrupt(self):
        with patch('hibernate_sql.bootstrap.ThreadingHTTPServer') as server_factory:
            with patch('hibernate_sql.bootstrap.webbrowser.open') as browser:
                with redirect_stdout(io.StringIO()) as output:
                    server = server_factory.return_value.__enter__.return_value
                    server.server_port = 12345
                    server.serve_forever.side_effect = KeyboardInterrupt
                    main(['--port', '0'])
        server_factory.assert_called_once_with(('127.0.0.1', 0), Handler)
        browser.assert_called_once_with('http://127.0.0.1:12345')
        self.assertIn('http://127.0.0.1:12345', output.getvalue())
        server_factory.return_value.__exit__.assert_called_once()

    def test_no_browser_and_default_port(self):
        with patch('hibernate_sql.bootstrap.ThreadingHTTPServer') as server_factory:
            with patch('hibernate_sql.bootstrap.webbrowser.open') as browser:
                with redirect_stdout(io.StringIO()):
                    main(['--no-browser'])
        browser.assert_not_called()
        server_factory.assert_called_once_with(('127.0.0.1', 8765), Handler)

    def test_invalid_cli_arguments_fail_before_starting_server(self):
        with patch('hibernate_sql.bootstrap.ThreadingHTTPServer') as server_factory:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(['--port', '99999'])
        self.assertEqual(error.exception.code, 2)
        server_factory.assert_not_called()

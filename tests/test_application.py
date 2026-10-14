import unittest
from unittest.mock import Mock

from converter import convert
from hibernate_sql.application.conversion import ConversionResult, ConversionService
from hibernate_sql.domain.models import Binding, Query
from hibernate_sql.infrastructure.hibernate_logs import HibernateLogParser


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.service = ConversionService(HibernateLogParser())

    def test_parser_is_injected(self):
        parser = Mock()
        parser.parse.return_value = [Query('select ?', {1: Binding('INTEGER', '7')})]
        self.assertEqual(ConversionService(parser).convert('source'), ['select 7'])
        parser.parse.assert_called_once_with('source')

    def test_empty_and_non_text_inputs(self):
        for log in ['', ' \n\t', None, 10, [], {}]:
            with self.subTest(log=log), self.assertRaises(ValueError):
                self.service.convert(log)

    def test_execute_formats_multiple_queries_and_semicolons(self):
        log = 'Hibernate: select 1;\nHibernate: select 2;'
        self.assertEqual(self.service.execute(log), ConversionResult('select 1\n;\n\nselect 2\n;', 2))
        expected = 'EXPLAIN ANALYZE\nselect 1\n;\n\nEXPLAIN ANALYZE\nselect 2\n;'
        self.assertEqual(self.service.execute(log, 'EXPLAIN ANALYZE').sql, expected)

    def test_custom_prefixes_are_copied(self):
        prefixes = {'Plano': 'EXPLAIN'}
        service = ConversionService(HibernateLogParser(), prefixes)
        prefixes.clear()
        self.assertEqual(service.execute('select 1', 'Plano').sql, 'EXPLAIN\nselect 1\n;')
        self.assertEqual(ConversionService(HibernateLogParser(), {}).prefixes, {})

    def test_invalid_prefixes(self):
        for prefix in ['DROP', None, 1, [], {}]:
            with self.subTest(prefix=prefix):
                with self.assertRaisesRegex(ValueError, 'Prefixo inválido'):
                    self.service.execute('select 1', prefix)

    def test_repeated_executions_with_bindings_are_preserved(self):
        log = '\n'.join([
            'Hibernate: select ?', 'binding parameter (1:INT) <- [1]',
            'Hibernate: select ?', 'binding parameter (1:INT) <- [2]',
        ])
        self.assertEqual(convert(log), ['select 1', 'select 2'])

    def test_duplicate_unbound_queries_are_collapsed(self):
        self.assertEqual(convert('org.hibernate.SQL : select 1\nHibernate: select 1'), ['select 1'])


class LogParserTests(unittest.TestCase):
    def test_noise_before_and_after_sql_is_ignored(self):
        log = '\n'.join([
            'Starting application', '2026-10-08T11:00:00 INFO ready',
            'Hibernate: select', '', ' ?', '2026-10-08T11:00:01 DEBUG message',
            'ignored continuation', 'binding parameter (1:INT) <- [9]',
        ])
        self.assertEqual(convert(log), ['select\n\n 9'])

    def test_raw_sql_and_multiline_logger_header(self):
        self.assertEqual(convert(' \nSELECT\n 1'), ['SELECT\n 1'])
        self.assertEqual(convert('org.hibernate.SQL :\n select 1'), ['select 1'])

    def test_non_sql_input_and_empty_sql_blocks(self):
        logs = [
            '2026-10-08T11:00:00 INFO ready', 'just random text',
            'Hibernate:', 'Hibernate:\nHibernate: select 1',
        ]
        for log in logs:
            with self.subTest(log=log), self.assertRaisesRegex(ValueError, 'SQL'):
                convert(log)

    def test_binding_without_query(self):
        with self.assertRaisesRegex(ValueError, 'sem uma SQL anterior'):
            convert('binding parameter (1:INT) <- [1]')

    def test_malformed_binding_is_rejected(self):
        bindings = [
            'binding parameter (x:INT) <- [1]',
            'binding parameter (1:INT) <- [truncated',
            'binding parameter (-1:INT) <- [1]',
        ]
        for binding in bindings:
            with self.subTest(binding=binding):
                with self.assertRaisesRegex(ValueError, 'binding inválida'):
                    convert('Hibernate: select ?\n' + binding)

    def test_brackets_and_whitespace_in_text_values(self):
        log = 'Hibernate: select ?\nbinding parameter (1:VARCHAR) <- [ a[b] ]'
        self.assertEqual(convert(log), ["select E' a[b] '"])

    def test_binding_words_inside_sql_text_are_preserved(self):
        sql = "select 'binding parameter (1:INT) <- [1]'"
        self.assertEqual(convert(sql), [sql])

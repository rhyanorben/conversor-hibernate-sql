import unittest

from converter import convert
from hibernate_sql.infrastructure.hibernate_logs import HibernateLogParser


def record(thread, message, logger='org.hibernate.SQL', style='spring'):
    if style == 'spring':
        return f'2026-10-20T10:00:00.000-03:00 DEBUG 123 --- [my-app] [{thread}] {logger} : {message}'
    if style == 'single':
        return f'2026-10-20 10:00:00 DEBUG [{thread}] {logger} : {message}'
    return f'10:00:00.000 [{thread}] DEBUG {logger} - {message}'


def bind(thread, value, position=1, kind='INTEGER', style='spring'):
    return record(thread, f'binding parameter ({position}:{kind}) <- [{value}]',
                  'org.hibernate.orm.jdbc.bind', style)


class ThreadSeparationTests(unittest.TestCase):
    def test_interleaved_threads_keep_their_own_bindings_and_sql_order(self):
        for style in ['spring', 'single', 'logback']:
            with self.subTest(style=style):
                log = '\n'.join([
                    record('worker-1', 'select ?, ?', style=style),
                    record('worker-2', 'select ?', style=style),
                    bind('worker-2', '20', style=style),
                    bind('worker-1', '12', position=2, style=style),
                    bind('worker-1', '11', style=style),
                ])
                self.assertEqual(convert(log), ['select 11, 12', 'select 20'])

    def test_successive_executions_on_the_same_thread_have_separate_bindings(self):
        log = '\n'.join([
            record('one', 'select ?'), record('two', 'select ?'),
            bind('one', '1'), record('one', 'select ?'),
            bind('two', '2'), bind('one', '3'),
        ])
        self.assertEqual(convert(log), ['select 1', 'select 2', 'select 3'])

    def test_identical_unbound_sql_on_different_threads_is_not_deduplicated(self):
        log = '\n'.join([record('one', 'select 1'), record('two', 'select 1')])
        self.assertEqual(convert(log), ['select 1', 'select 1'])

    def test_multiline_sql_preserves_brackets_and_protected_question_marks(self):
        log = '\n'.join([
            record('one', 'select'), " ?, '[not a thread]?',", ' ?',
            record('two', "select ?, '[other]?'"),
            bind('two', '[value]', kind='VARCHAR'),
            bind('one', '11'), bind('one', '12', position=2),
        ])
        self.assertEqual(convert(log), ["select\n 11, '[not a thread]?',\n 12",
                                        "select E'[value]', '[other]?'"])

    def test_show_sql_echo_is_matched_to_its_thread_even_when_bindings_interleave(self):
        sql = 'select\n ?'
        log = '\n'.join([
            record('one', sql), 'Hibernate: ' + sql,
            record('two', 'select ?'), 'Hibernate: select ?',
            bind('two', '2'), bind('one', '1'),
        ])
        self.assertEqual(convert(log), ['select\n 1', 'select 2'])

    def test_show_sql_echo_does_not_leave_a_stale_unthreaded_alias(self):
        log = '\n'.join([
            record('one', 'select ?'), 'Hibernate: select ?', bind('one', '1'),
            record('one', 'select ?'), 'binding parameter (1:INTEGER) <- [2]',
        ])
        self.assertEqual(convert(log), ['select 1', 'select 2'])

    def test_a_single_show_sql_record_can_be_identified_by_its_threaded_binding(self):
        log = 'Hibernate: select ?\n' + bind('one', '1')
        self.assertEqual(convert(log), ['select 1'])

    def test_unknown_thread_never_borrows_another_threads_sql(self):
        with self.assertRaisesRegex(ValueError, r'Linha 2, thread two, parâmetro 1: .*sem uma SQL anterior'):
            convert(record('one', 'select ?') + '\n' + bind('two', '2'))

    def test_threadless_binding_in_mixed_logs_is_rejected_as_ambiguous(self):
        log = '\n'.join([
            record('one', 'select ?'), record('two', 'select ?'),
            'binding parameter (1:INTEGER) <- [1]',
        ])
        with self.assertRaisesRegex(ValueError, r'Linha 3: .*sem identificação de thread'):
            convert(log)

    def test_noise_ends_a_multiline_sql_record_without_losing_its_active_thread(self):
        for noise in ['2026-10-20T10:00:00 INFO ready', '10:00:00.000 [two] INFO ready', '[two] INFO ready']:
            with self.subTest(noise=noise):
                log = '\n'.join([record('one', 'select ?'), noise, 'ignored continuation', bind('one', '1')])
                self.assertEqual(convert(log), ['select 1'])


class DiagnosticTests(unittest.TestCase):
    def assert_diagnostic(self, log, *parts):
        with self.assertRaises(ValueError) as raised:
            convert(log)
        for part in parts:
            self.assertIn(part, str(raised.exception))

    def test_missing_parameter_identifies_query_sql_line_and_thread(self):
        log = '\n'.join([record('one', 'select ?'), record('two', 'select ?, ?'),
                         bind('one', '1'), bind('two', '2')])
        self.assert_diagnostic(log, 'Query 2', 'SQL na linha 2', 'thread two', 'parâmetro 2', 'Falta')

    def test_invalid_values_identify_the_binding_line_and_parameter(self):
        for kind, value, error in [('INTEGER', 'abc', 'numérico inválido'),
                                    ('BOOLEAN', 'yes', 'Booleano inválido'),
                                    ('DOUBLE', 'Infinity', 'não finito')]:
            with self.subTest(kind=kind):
                log = '\n'.join(['Hibernate: select 1', record('two', 'select ?'),
                                 bind('two', value, kind=kind)])
                self.assert_diagnostic(log, 'Query 2', 'SQL na linha 2', 'thread two',
                                       'parâmetro 1', 'linha 3', error)

    def test_duplicate_zero_and_malformed_parameters_have_source_locations(self):
        for binding, parameter, error in [
            (bind('one', '2'), '1', 'repetido'),
            (bind('one', '2', position=0), '0', 'inválido'),
            (bind('one', '2', position='x'), 'x', 'binding inválida'),
            (bind('one', '2')[:-1], '1', 'binding inválida'),
        ]:
            with self.subTest(binding=binding):
                log = '\n'.join([record('one', 'select ?'), bind('one', '1'), binding])
                self.assert_diagnostic(log, 'Query 1', 'SQL na linha 1', 'thread one',
                                       'parâmetro ' + parameter, 'linha 3', error)

    def test_extra_parameter_identifies_the_binding_line(self):
        log = '\n'.join([record('one', 'select ?'), bind('one', '1'), bind('one', '2', position=2)])
        self.assert_diagnostic(log, 'Query 1', 'parâmetro 2', 'linha 3', 'excedentes: 2')

    def test_sql_syntax_regions_and_empty_blocks_identify_query_and_source(self):
        for sql, error in [("select '", 'aspas sem fechamento'), ('', 'bloco SQL vazio')]:
            with self.subTest(sql=sql):
                self.assert_diagnostic('Hibernate: select 1\n' + record('two', sql),
                                       'Query 2', 'SQL na linha 2', 'thread two', error)

    def test_duplicate_echoes_do_not_inflate_the_query_number_in_parser_errors(self):
        log = '\n'.join(['org.hibernate.SQL : select 1', 'Hibernate: select 1',
                         'Hibernate: select ?', 'binding parameter (x:INTEGER) <- [1]'])
        self.assert_diagnostic(log, 'Query 2', 'SQL na linha 3', 'linha 4', 'parâmetro x')

    def test_query_metadata_tracks_original_lines_including_blank_lines(self):
        log = '\n' + record('one', 'select ?') + '\n\n' + bind('one', '1')
        query, = HibernateLogParser().parse(log)
        self.assertEqual(query.line_number, 2)
        self.assertEqual(query.binding_lines, {1: 4})
        self.assertEqual(query.thread, 'one')

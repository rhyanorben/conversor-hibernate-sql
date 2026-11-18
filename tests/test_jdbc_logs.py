import unittest
from pathlib import Path

from converter import convert
from hibernate_sql.infrastructure.hibernate_logs import HibernateLogParser


def sql(text='select ?', thread='worker-1', package='o.s'):
    return (f'-2026-11-18T09:58:41.923-03:00 -DEBUG [{thread}] '
            f'{package}.jdbc.core.JdbcTemplate : Executing prepared SQL statement [{text}]')


def bind(value, java_class='java.lang.String', position=1, thread='worker-1',
         sql_type='unknown', package='o.s'):
    return (f'-2026-11-18T09:58:41.924-03:00 -TRACE [{thread}] '
            f'{package}.jdbc.core.StatementCreatorUtils : Setting SQL statement parameter value: '
            f'column index {position}, parameter value [{value}], '
            f'value class [{java_class}], SQL type {sql_type}')


class JdbcLogTests(unittest.TestCase):
    def test_attached_query_with_24_parameters(self):
        log = (Path(__file__).with_name('fixtures') / 'jdbc-24.log').read_text()
        query, = HibernateLogParser().parse(log)
        self.assertEqual(len(query.parameters), 24)
        self.assertEqual(query.thread, 'http-nio-8')
        result, = convert(log)
        self.assertNotIn('?', result)
        self.assertTrue(result.startswith('SELECT p.idproduto'))
        self.assertTrue(result.endswith('ORDER BY p.idproduto'))
        self.assertEqual(result.count("E'2026-06-01T00:00-03:00'::timestamptz"), 2)
        self.assertEqual(result.count("E'2026-06-30T23:59:59.999999-03:00'::timestamptz"), 2)
        self.assertIn("CAST(E'{EXCLUSAO_REGISTROS,CONTROLE_VALE_GAS}' AS text[])", result)
        self.assertIn("CAST(E'{ATENDIMENTO,PEDIDO,CONTROLE_VALE_GAS}' AS text[])", result)
        self.assertEqual(result.count("CAST(E'{2532}' AS int[])"), 2)
        self.assertEqual(result.count('CAST(NULL AS int[])'), 4)
        self.assertEqual(result.count('idempresa = 2532'), 3)

    def test_classes_and_explicit_sql_types(self):
        cases = [
            ('java.lang.String', "D'Ávila\\[?]", 'unknown', "E'D''Ávila\\\\[?]'"),
            ('java.lang.Long', '2532', 'unknown', '2532'),
            ('java.math.BigDecimal', '12345678901234567890.01230', 'unknown', '12345678901234567890.01230'),
            ('java.lang.Boolean', 'true', 'unknown', 'TRUE'),
            ('java.time.LocalDate', '2026-06-01', 'unknown', "E'2026-06-01'::date"),
            ('java.lang.String', '42', '4', '42'),
            ('java.lang.String', '', '12', "E''"),
            ('null', 'null', 'unknown', 'NULL'),
        ]
        for java_class, value, sql_type, expected in cases:
            for package in ['o.s', 'org.springframework']:
                with self.subTest(java_class=java_class, package=package):
                    self.assertEqual(convert(sql(package=package) + '\n' + bind(
                        value, java_class, sql_type=sql_type, package=package)), ['select ' + expected])

    def test_multiline_arrays_and_out_of_order_parameters(self):
        log = '\n'.join([sql("select\n CAST(? AS text[]), ARRAY[?], '[?]'"),
                         bind('2', 'java.lang.Integer', position=2), bind('{A,B}')])
        self.assertEqual(convert(log), ["select\n CAST(E'{A,B}' AS text[]), ARRAY[2], '[?]'"])

    def test_interleaved_jdbc_and_hibernate(self):
        log = '\n'.join([sql(),
                         'DEBUG [worker-2] org.hibernate.SQL : select ?',
                         sql(thread='worker-3'), bind('third', thread='worker-3'),
                         'TRACE [worker-2] org.hibernate.orm.jdbc.bind : binding parameter (1:INTEGER) <- [2]',
                         bind('first'), sql(), bind('next')])
        self.assertEqual(convert(log), ["select E'first'", 'select 2', "select E'third'", "select E'next'"])

    def test_noise_does_not_become_part_of_sql(self):
        log = '\n'.join([sql(), '-2026-11-18T09:58:41 -DEBUG [worker-2] other.Logger : noise',
                         'ignored continuation', bind('ok')])
        self.assertEqual(convert(log), ["select E'ok'"])

    def test_invalid_bindings_keep_source_context(self):
        for line, error in [(bind('x', 'java.lang.Integer'), 'numérico inválido'),
                            (bind('x', position=0), 'Índice de parâmetro inválido'),
                            (bind('x', position='x'), 'binding inválida'),
                            (bind('x')[:-1], 'binding inválida')]:
            with self.subTest(line=line), self.assertRaisesRegex(
                    ValueError, 'Query 1, SQL na linha 1, thread worker-1, parâmetro .*linha 2: .*' + error):
                convert(sql() + '\n' + line)
        with self.assertRaisesRegex(ValueError, 'repetido'):
            convert('\n'.join([sql(), bind('x'), bind('y')]))
        with self.assertRaisesRegex(ValueError, 'Falta o parâmetro 1'):
            convert(sql())
        with self.assertRaisesRegex(ValueError, 'excedentes: 2'):
            convert('\n'.join([sql(), bind('x'), bind('y', position=2)]))
        with self.assertRaisesRegex(ValueError, 'sem uma SQL anterior'):
            convert(bind('x'))
        with self.assertRaisesRegex(ValueError, 'sem fechamento'):
            convert(sql()[:-1])

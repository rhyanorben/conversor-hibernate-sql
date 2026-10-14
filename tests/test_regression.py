import unittest
from pathlib import Path

from converter import convert


class ConverterRegressionTests(unittest.TestCase):
    def test_attached_multiline_sql_with_70_parameters(self):
        fixture = Path(__file__).with_name('fixtures') / 'multiline-70.log'
        result = convert(fixture.read_text(encoding='utf-8'))
        self.assertEqual(len(result), 1)
        self.assertNotIn('?', result[0])
        self.assertIn("t.dtvencimento < E'2026-10-08'::date", result[0])
        self.assertIn('WHERE t.idempresa = 74', result[0])
        self.assertEqual(result[0].count('IS FALSE'), 6)
        self.assertIn("t.dsobservacao ILIKE concat('%', E'', '%')", result[0])

    def test_duplicate_multiline_preserves_comments_and_empty_lines(self):
        sql = "select\n ? -- keep this comment\n\n , '?'"
        log = '\n'.join([
            'org.hibernate.SQL : ' + sql,
            'Hibernate: ' + sql,
            'binding parameter (1:INTEGER) <- [42]',
        ])
        self.assertEqual(convert(log), ["select\n 42 -- keep this comment\n\n , '?'"])

    def test_ten_parameters_and_duplicate_sql(self):
        placeholders = ','.join(['?'] * 10)
        sql = 'select * from gestao.tbcontas_receber_titulo where idtitulo in (' + placeholders + ')'
        ids = [
            1292112, 1292214, 1292227, 1292228, 1304911,
            1304912, 1304913, 1304919, 1304935, 1304937,
        ]
        logger = '2026-10-08T10:21:58.906-03:00 DEBUG 658538 --- '
        logger += '[gestao-service] [nio-8183-exec-1] org.hibernate.SQL : '
        lines = [logger + sql, 'Hibernate: ' + sql]
        bind_logger = '2026-10-08T10:21:58.906-03:00 TRACE 658538 --- '
        bind_logger += '[gestao-service] [nio-8183-exec-1] org.hibernate.orm.jdbc.bind : '
        for index, value in reversed(list(enumerate(ids, 1))):
            lines.append(bind_logger + f'binding parameter ({index}:BIGINT) <- [{value}]')
        expected = sql.replace(placeholders, ','.join(map(str, ids)))
        self.assertEqual(convert('\n'.join(lines)), [expected])

    def test_postgres_literals(self):
        values = [
            ('VARCHAR', "D'Ávila\\pasta"), ('DATE', '2026-10-08'),
            ('BOOLEAN', 'true'), ('NUMERIC', '12.50'),
            ('VARCHAR', 'null'), ('VARCHAR', 'a[b]'),
        ]
        lines = ['Hibernate: select ?, ?, ?, ?, ?, ?']
        lines.extend(
            f'binding parameter ({index}:{kind}) <- [{value}]'
            for index, (kind, value) in enumerate(values, 1)
        )
        expected = "select E'D''Ávila\\\\pasta', E'2026-10-08'::date, TRUE, 12.50, NULL, E'a[b]'"
        self.assertEqual(convert('\n'.join(lines)), [expected])

    def test_quoted_questions_and_comments(self):
        sql = "select '?', \"?\", $$?$$, $body$?$body$, E'it\\'s?', ? /* ? /* ? */ */ -- ?\n"
        log = 'Hibernate: ' + sql + 'binding parameter (1:INTEGER) <- [42]'
        self.assertEqual(convert(log), [sql.replace(', ? /*', ', 42 /*').strip()])

    def test_several_queries_and_multiline(self):
        log = '\n'.join([
            'Hibernate: select', ' ?', 'binding parameter (1:INTEGER) <- [1]',
            'Hibernate: select ?', 'binding parameter (1:INTEGER) <- [2]',
        ])
        self.assertEqual(convert(log), ['select\n 1', 'select 2'])

    def test_missing_extra_and_duplicate_parameters(self):
        logs = [
            'Hibernate: select ?',
            'Hibernate: select 1\nbinding parameter (1:INTEGER) <- [1]',
            '\n'.join([
                'Hibernate: select ?', 'binding parameter (1:INTEGER) <- [1]',
                'binding parameter (1:INTEGER) <- [2]',
            ]),
        ]
        for log in logs:
            with self.subTest(log=log), self.assertRaises(ValueError):
                convert(log)

import json
import threading
import unittest
from pathlib import Path
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from app import Handler
from converter import convert


class ConverterTests(unittest.TestCase):
    def test_attached_multiline_sql_with_70_parameters(self):
        log = Path(__file__).with_name('multiline-70.log').read_text()
        result = convert(log)
        self.assertEqual(len(result), 1)
        self.assertNotIn('?', result[0])
        self.assertIn("t.dtvencimento < E'2026-10-08'::date", result[0])
        self.assertIn('WHERE t.idempresa = 74', result[0])
        self.assertEqual(result[0].count('IS FALSE'), 6)
        self.assertIn("t.dsobservacao ILIKE concat('%', E'', '%')", result[0])

    def test_duplicate_multiline_preserves_comments_and_empty_lines(self):
        sql = "select\n ? -- keep this comment\n\n , '?'"
        log = 'org.hibernate.SQL : ' + sql + '\nHibernate: ' + sql + '\nbinding parameter (1:INTEGER) <- [42]'
        self.assertEqual(convert(log), ["select\n 42 -- keep this comment\n , '?'"])

    def test_ten_parameters_and_duplicate_sql(self):
        sql = 'select * from gestao.tbcontas_receber_titulo where idtitulo in (' + ','.join(['?'] * 10) + ')'
        ids = [1292112, 1292214, 1292227, 1292228, 1304911, 1304912, 1304913, 1304919, 1304935, 1304937]
        log = '2026-10-08T10:21:58.906-03:00 DEBUG 658538 --- [gestao-service] [nio-8183-exec-1] org.hibernate.SQL : ' + sql + '\nHibernate: ' + sql
        for index, value in reversed(list(enumerate(ids, 1))):
            log += f'\n2026-10-08T10:21:58.906-03:00 TRACE 658538 --- [gestao-service] [nio-8183-exec-1] org.hibernate.orm.jdbc.bind : binding parameter ({index}:BIGINT) <- [{value}]'
        self.assertEqual(convert(log), [sql.replace(','.join(['?'] * 10), ','.join(map(str, ids)))])

    def test_postgres_literals(self):
        log = "Hibernate: select ?, ?, ?, ?, ?, ?\n"
        values = [('VARCHAR', "D'Ávila\\pasta"), ('DATE', '2026-10-08'), ('BOOLEAN', 'true'), ('NUMERIC', '12.50'), ('VARCHAR', 'null'), ('VARCHAR', 'a[b]')]
        log += '\n'.join(f'binding parameter ({i}:{kind}) <- [{value}]' for i, (kind, value) in enumerate(values, 1))
        self.assertEqual(convert(log), ["select E'D''Ávila\\\\pasta', E'2026-10-08'::date, TRUE, 12.50, NULL, E'a[b]'"])

    def test_quoted_questions_and_comments(self):
        sql = "select '?', \"?\", $$?$$, $body$?$body$, E'it\\'s?', ? /* ? /* ? */ */ -- ?\n"
        self.assertEqual(convert('Hibernate: ' + sql + 'binding parameter (1:INTEGER) <- [42]'), [sql.replace(', ? /*', ', 42 /*').strip()])

    def test_several_queries_and_multiline(self):
        log = 'Hibernate: select\n ?\nbinding parameter (1:INTEGER) <- [1]\nHibernate: select ?\nbinding parameter (1:INTEGER) <- [2]'
        self.assertEqual(convert(log), ['select\n 1', 'select 2'])

    def test_missing_extra_and_duplicate_parameters(self):
        for log in ['Hibernate: select ?', 'Hibernate: select 1\nbinding parameter (1:INTEGER) <- [1]', 'Hibernate: select ?\nbinding parameter (1:INTEGER) <- [1]\nbinding parameter (1:INTEGER) <- [2]']:
            with self.subTest(log=log), self.assertRaises(ValueError):
                convert(log)

    def test_http_interface(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection('127.0.0.1', server.server_port)
        try:
            connection.request('GET', '/')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('Montar query', response.read().decode())
            connection.request('POST', '/convert', json.dumps({'log': 'Hibernate: select ?\nbinding parameter (1:BIGINT) <- [1292112]', 'prefix': 'EXPLAIN ANALYZE'}), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['sql'], 'EXPLAIN ANALYZE\nselect 1292112\n;')
            connection.request('POST', '/convert', json.dumps({'log': 'Hibernate: select ?'}), {'Content-Type': 'application/json'})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn('Falta o parâmetro 1', json.loads(response.read())['error'])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()

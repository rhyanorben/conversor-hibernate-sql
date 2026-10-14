import unittest

from converter import literal, substitute
from hibernate_sql.domain.literals import NUMBER_TYPES, TYPE_CASTS
from hibernate_sql.domain.models import Binding, Query


class LiteralTests(unittest.TestCase):
    def test_numeric_types_preserve_precision_and_sign(self):
        for kind in NUMBER_TYPES:
            with self.subTest(kind=kind):
                value = '-12345678901234567890.01230'
                self.assertEqual(literal(kind, value), value)
        self.assertEqual(literal(' decimal ', '1e3'), '1E+3')

    def test_invalid_and_non_finite_numbers_are_rejected(self):
        for value in ['abc', '', 'NaN', 'sNaN', 'Infinity', '-Infinity', '1; drop table users']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'numérico'):
                literal('INTEGER', value)

    def test_boolean_types_and_values(self):
        for kind in ['BOOLEAN', 'BOOL', 'BIT', ' bool ']:
            values = [('true', 'TRUE'), ('TRUE', 'TRUE'), ('1', 'TRUE'),
                      ('false', 'FALSE'), ('0', 'FALSE')]
            for value, expected in values:
                with self.subTest(kind=kind, value=value):
                    self.assertEqual(literal(kind, value), expected)
        with self.assertRaisesRegex(ValueError, 'Booleano inválido'):
            literal('BOOLEAN', 'yes')

    def test_null_and_unknown_types(self):
        for kind in ['INTEGER', 'BOOLEAN', 'VARCHAR', 'OTHER']:
            self.assertEqual(literal(kind, 'NuLl'), 'NULL')
        self.assertEqual(literal('OTHER', ''), "E''")
        self.assertEqual(literal('VARCHAR', ' null '), "E' null '")

    def test_casts_and_string_escaping(self):
        for kind, cast in TYPE_CASTS.items():
            with self.subTest(kind=kind):
                self.assertEqual(literal(kind, 'value'), f"E'value'::{cast}")
        self.assertEqual(literal('VARCHAR', "á'\\\n[]"), "E'á''\\\\\n[]'")


class SubstitutionTests(unittest.TestCase):
    def test_protected_regions_preserve_questions(self):
        regions = [
            "'it''s ?'", '"a""?"', '$$?$$', '$tag_1$?$tag_1$',
            "E'it\\'s ?'", "e'\\\\?'", '/* ? /* ? */ ? */', '-- ?\n',
        ]
        for region in regions:
            with self.subTest(region=region):
                self.assertEqual(substitute(f'select {region}, ?', {1: '7'}), f'select {region}, 7')

    def test_line_comment_at_end(self):
        self.assertEqual(substitute('select ? -- ?', {1: '1'}), 'select 1 -- ?')

    def test_unterminated_protected_regions_are_rejected(self):
        queries = [
            "select '", 'select "', "select E'abc\\", 'select /* nested /* */',
            'select $$abc', 'select $tag$abc',
        ]
        for sql in queries:
            with self.subTest(sql=sql), self.assertRaisesRegex(ValueError, 'sem fechamento'):
                substitute(sql, {})

    def test_dollar_identifiers_are_not_strings(self):
        self.assertEqual(substitute('select column$tag$, $1, ?', {1: '9'}), 'select column$tag$, $1, 9')

    def test_missing_and_extra_parameters(self):
        with self.assertRaisesRegex(ValueError, 'Falta o parâmetro 2'):
            substitute('select ?, ?', {1: '1'})
        with self.assertRaisesRegex(ValueError, 'excedentes: 2, 10'):
            substitute('select ?', {1: '1', 10: '10', 2: '2'})

    def test_repeated_and_zero_bindings_are_rejected(self):
        query = Query('select ?')
        query.add_binding(1, Binding('INTEGER', '1'))
        for position in [0, -1, 1]:
            with self.subTest(position=position):
                with self.assertRaisesRegex(ValueError, 'inválido ou repetido'):
                    query.add_binding(position, Binding('INTEGER', '2'))

    def test_queries_do_not_share_bindings(self):
        first = Query('select ?')
        second = Query('select ?')
        first.add_binding(1, Binding('INTEGER', '1'))
        self.assertEqual(second.parameters, {})

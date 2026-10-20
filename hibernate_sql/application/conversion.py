from dataclasses import dataclass
from typing import List, Mapping, Optional

from hibernate_sql.application.ports import QueryParser
from hibernate_sql.domain.literals import literal
from hibernate_sql.domain.models import ParameterError, Query
from hibernate_sql.domain.substitution import substitute


DEFAULT_PREFIXES = {'EXPLAIN ANALYZE': 'EXPLAIN ANALYZE'}


@dataclass(frozen=True)
class ConversionResult:
    sql: str
    count: int


def remove_duplicate_queries(queries: List[Query]) -> List[Query]:
    unique = []
    for query in queries:
        if (unique and not unique[-1].parameters
                and unique[-1].thread == query.thread
                and unique[-1].sql.strip() == query.sql.strip()):
            unique[-1] = query
        else:
            unique.append(query)
    return unique


class ConversionService:
    def __init__(self, parser: QueryParser, prefixes: Optional[Mapping[str, str]] = None):
        self.parser = parser
        self.prefixes = dict(DEFAULT_PREFIXES if prefixes is None else prefixes)

    def convert(self, log: str) -> List[str]:
        if not isinstance(log, str):
            raise ValueError('Informe os logs como texto.')
        if not log.strip():
            raise ValueError('Cole os logs do Hibernate primeiro.')
        queries = remove_duplicate_queries(self.parser.parse(log))
        converted = []
        for number, query in enumerate(queries, 1):
            parameters = {}
            for position, binding in query.parameters.items():
                try:
                    parameters[position] = literal(binding.kind, binding.value)
                except ValueError as error:
                    raise query.error(str(error), number, position, query.binding_lines.get(position)) from None
            try:
                converted.append(substitute(query.sql, parameters))
            except ParameterError as error:
                raise query.error(str(error), number, error.position,
                                  query.binding_lines.get(error.position)) from None
            except ValueError as error:
                raise query.error(str(error), number) from None
        return converted

    def execute(self, log: str, prefix_name: str = '') -> ConversionResult:
        if not isinstance(prefix_name, str) or prefix_name and prefix_name not in self.prefixes:
            raise ValueError('Prefixo inválido.')
        queries = self.convert(log)
        prefix = self.prefixes.get(prefix_name, '')
        output = '\n\n'.join(
            (prefix + '\n' if prefix else '') + sql.rstrip().rstrip(';') + '\n;'
            for sql in queries
        )
        return ConversionResult(output, len(queries))

import re
from typing import List

from hibernate_sql.domain.models import Binding, Query


BIND = re.compile(r'binding parameter\s*\((\d+):([^)]*)\)\s*<-\s*\[(.*)\]\s*$')
BIND_LOG = re.compile(
    r'^\s*binding parameter\b|org\.hibernate\.orm\.jdbc\.bind\s*(?::|-)\s*binding parameter\b'
)
BIND_POSITION = re.compile(r'binding parameter\s*\(([^:)]*)')
SQL_LOG = re.compile(r'(?:org\.hibernate\.SQL\s*(?::|-)\s*|^\s*Hibernate:\s*)(.*)$')
JDBC_SQL_LOG = re.compile(
    r'(?:org\.springframework|o\.s)\.jdbc\.core\.JdbcTemplate\s*(?::|-)\s*'
    r'Executing prepared SQL statement \[(.*)$'
)
JDBC_BIND_LOG = re.compile(
    r'(?:org\.springframework|o\.s)\.jdbc\.core\.StatementCreatorUtils\s*(?::|-)\s*'
    r'Setting SQL statement parameter value:'
)
JDBC_BIND = re.compile(
    r'Setting SQL statement parameter value: column index (\d+), '
    r'parameter value \[(.*)\], value class \[([^\]]*)\], SQL type (unknown|-?\d+)\s*$'
)
JDBC_POSITION = re.compile(r'column index ([^,]*)')
JAVA_TYPES = {
    'java.lang.Byte': 'TINYINT', 'java.lang.Short': 'SMALLINT',
    'java.lang.Integer': 'INTEGER', 'java.lang.Long': 'BIGINT',
    'java.math.BigInteger': 'NUMERIC', 'java.math.BigDecimal': 'DECIMAL',
    'java.lang.Float': 'FLOAT', 'java.lang.Double': 'DOUBLE',
    'java.lang.Boolean': 'BOOLEAN',
    'java.sql.Date': 'DATE', 'java.time.LocalDate': 'DATE',
    'java.sql.Time': 'TIME', 'java.time.LocalTime': 'TIME',
    'java.sql.Timestamp': 'TIMESTAMP', 'java.time.LocalDateTime': 'TIMESTAMP',
    'java.time.OffsetDateTime': 'TIMESTAMP_WITH_TIMEZONE',
    'java.time.OffsetTime': 'TIME_WITH_TIMEZONE', 'java.util.UUID': 'UUID',
}
JDBC_TYPES = {
    '-7': 'BIT', '-6': 'TINYINT', '-5': 'BIGINT', '5': 'SMALLINT',
    '4': 'INTEGER', '2': 'NUMERIC', '3': 'DECIMAL', '6': 'FLOAT',
    '7': 'REAL', '8': 'DOUBLE', '16': 'BOOLEAN', '91': 'DATE',
    '92': 'TIME', '93': 'TIMESTAMP', '2013': 'TIME_WITH_TIMEZONE',
    '2014': 'TIMESTAMP_WITH_TIMEZONE',
}
LOG_START = re.compile(
    r'^\s*-?(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|'
    r'\[[^\]]+\]\s+(?:TRACE|DEBUG|INFO|WARN|ERROR)\b)'
)
THREAD = re.compile(r'\[([^\[\]]+)\]')
RAW_SQL_START = re.compile(
    r'^\s*(?:select|with|insert|update|delete|merge|values|explain|'
    r'create|alter|drop|truncate|call|do|begin|commit|rollback|set|show)\b',
    re.IGNORECASE,
)


def thread_before(line, match):
    # Read only the logger prefix: brackets in SQL or parameter values are data.
    groups = THREAD.findall(line[:match.start()])
    return groups[-1].strip() if groups else None


class HibernateLogParser:
    def parse(self, log: str) -> List[Query]:
        queries = []
        active = {}
        collecting = None
        duplicate_candidate = None
        jdbc_collecting = False

        def finish_sql():
            nonlocal collecting, duplicate_candidate, jdbc_collecting
            if collecting is not None and jdbc_collecting:
                sql = collecting.sql.rstrip()
                if not sql.endswith(']'):
                    raise collecting.error('Registro SQL JDBC sem fechamento ].', queries.index(collecting) + 1)
                # Remove only the logger wrapper; PostgreSQL arrays also use brackets.
                collecting.sql = sql[:-1].strip()
            jdbc_collecting = False
            if (collecting is not None and duplicate_candidate is not None
                    and collecting.sql.strip() == duplicate_candidate.sql.strip()
                    and not duplicate_candidate.parameters):
                # Hibernate show_sql can repeat a threaded logger record without
                # any prefix. Keep its thread so subsequent binds find this copy.
                collecting.thread = duplicate_candidate.thread
                collecting.line_number = duplicate_candidate.line_number
                if collecting.thread is not None and active.get(None) is collecting:
                    active.pop(None)
                active[collecting.thread] = collecting
                queries.pop(-2)
            collecting = None
            duplicate_candidate = None

        def fail(message, line_number, thread=None, query=None, parameter=None):
            if query is not None:
                raise query.error(message, queries.index(query) + 1, parameter, line_number)
            context = f'Linha {line_number}'
            if thread is not None:
                context += f', thread {thread}'
            if parameter is not None:
                context += f', parâmetro {parameter}'
            raise ValueError(context + ': ' + message)

        for line_number, line in enumerate(log.splitlines(), 1):
            jdbc_sql = JDBC_SQL_LOG.search(line)
            sql_match = jdbc_sql or SQL_LOG.search(line)
            jdbc_bind = JDBC_BIND_LOG.search(line)
            bind_log = jdbc_bind or BIND_LOG.search(line)
            if sql_match:
                finish_sql()
                jdbc_collecting = jdbc_sql is not None
                previous = queries[-1] if queries else None
                thread = thread_before(line, sql_match)
                collecting = Query(sql_match.group(1).strip(), line_number=line_number, thread=thread)
                if previous is not None and (thread is None or thread == previous.thread):
                    duplicate_candidate = previous
                queries.append(collecting)
                active[thread] = collecting
            elif bind_log:
                finish_sql()
                thread = thread_before(line, bind_log)
                query = active.get(thread)
                if thread is None:
                    candidates = {id(item): item for item in active.values()}
                    if len(candidates) > 1:
                        fail('Binding sem identificação de thread em logs intercalados. '
                             'Inclua a thread no formato do logger ou separe as execuções.', line_number)
                    query = next(iter(candidates.values()), None)
                elif query is None and set(active) == {None}:
                    # show_sql-only output can still have threaded bind records.
                    query = active.pop(None)
                    query.thread = thread
                    active[thread] = query
                bind_match = (JDBC_BIND if jdbc_bind else BIND).search(line)
                position_match = (JDBC_POSITION if jdbc_bind else BIND_POSITION).search(line)
                position_text = position_match.group(1) if position_match else None
                if query is None:
                    fail('Encontrado binding sem uma SQL anterior para esta thread.',
                         line_number, thread, parameter=position_text)
                if not bind_match:
                    fail('Linha de binding inválida. Cole o registro completo.',
                         line_number, thread, query, position_text)
                if jdbc_bind:
                    position, value, java_class, sql_type = bind_match.groups()
                    kind = JDBC_TYPES.get(sql_type, JAVA_TYPES.get(java_class, 'VARCHAR'))
                else:
                    position, kind, value = bind_match.groups()
                try:
                    position = int(position)
                    query.add_binding(position, Binding(kind, value))
                except ValueError as error:
                    fail(str(error), line_number, thread, query, position_text)
                query.binding_lines[position] = line_number
            elif LOG_START.match(line):
                finish_sql()
            elif collecting is not None:
                collecting.sql += '\n' + line
            elif not queries and RAW_SQL_START.match(line):
                collecting = Query(line.strip(), line_number=line_number)
                queries.append(collecting)
                active[None] = collecting
        finish_sql()
        if not queries:
            raise ValueError('Nenhuma SQL encontrada nos logs.')
        for number, query in enumerate(queries, 1):
            if not query.sql.strip():
                raise query.error('Encontrado bloco SQL vazio.', number)
        return queries

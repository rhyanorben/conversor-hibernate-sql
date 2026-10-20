import re
from typing import List

from hibernate_sql.domain.models import Binding, Query


BIND = re.compile(r'binding parameter\s*\((\d+):([^)]*)\)\s*<-\s*\[(.*)\]\s*$')
BIND_LOG = re.compile(
    r'^\s*binding parameter\b|org\.hibernate\.orm\.jdbc\.bind\s*(?::|-)\s*binding parameter\b'
)
BIND_POSITION = re.compile(r'binding parameter\s*\(([^:)]*)')
SQL_LOG = re.compile(r'(?:org\.hibernate\.SQL\s*(?::|-)\s*|^\s*Hibernate:\s*)(.*)$')
LOG_START = re.compile(
    r'^\s*(?:\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|'
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

        def finish_sql():
            nonlocal collecting, duplicate_candidate
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
            sql_match = SQL_LOG.search(line)
            bind_log = BIND_LOG.search(line)
            if sql_match:
                finish_sql()
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
                bind_match = BIND.search(line)
                position_match = BIND_POSITION.search(line)
                position_text = position_match.group(1) if position_match else None
                if query is None:
                    fail('Encontrado binding sem uma SQL anterior para esta thread.',
                         line_number, thread, parameter=position_text)
                if not bind_match:
                    fail('Linha de binding inválida. Cole o registro completo.',
                         line_number, thread, query, position_text)
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

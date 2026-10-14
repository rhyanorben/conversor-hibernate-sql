import re
from typing import List

from hibernate_sql.domain.models import Binding, Query


BIND = re.compile(r'binding parameter\s*\((\d+):([^)]*)\)\s*<-\s*\[(.*)\]\s*$')
BIND_LOG = re.compile(
    r'^\s*binding parameter\b|org\.hibernate\.orm\.jdbc\.bind\s*:\s*binding parameter\b'
)
SQL_LOG = re.compile(r'(?:org\.hibernate\.SQL\s*:\s*|^\s*Hibernate:\s*)(.*)$')
LOG_START = re.compile(r'^\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')
RAW_SQL_START = re.compile(
    r'^\s*(?:select|with|insert|update|delete|merge|values|explain|'
    r'create|alter|drop|truncate|call|do|begin|commit|rollback|set|show)\b',
    re.IGNORECASE,
)


class HibernateLogParser:
    def parse(self, log: str) -> List[Query]:
        queries = []
        current = None
        collecting = False
        for line in log.splitlines():
            sql_match = SQL_LOG.search(line)
            bind_match = BIND.search(line) if BIND_LOG.search(line) else None
            if sql_match:
                current = Query(sql_match.group(1).strip())
                queries.append(current)
                collecting = True
            elif bind_match:
                if current is None:
                    raise ValueError('Encontrado binding sem uma SQL anterior.')
                position, kind, value = bind_match.groups()
                current.add_binding(int(position), Binding(kind, value))
                collecting = False
            elif BIND_LOG.search(line):
                raise ValueError('Linha de binding inválida. Cole o registro completo.')
            elif LOG_START.match(line):
                collecting = False
            elif collecting:
                current.sql += '\n' + line
            elif current is None and RAW_SQL_START.match(line):
                current = Query(line.strip())
                queries.append(current)
                collecting = True
        if not queries:
            raise ValueError('Nenhuma SQL encontrada nos logs.')
        if any(not query.sql.strip() for query in queries):
            raise ValueError('Encontrado bloco SQL vazio.')
        return queries

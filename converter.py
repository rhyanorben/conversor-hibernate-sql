"""Reconstrói SQL PostgreSQL a partir de SQL e binds do Hibernate."""
import re
from decimal import Decimal, InvalidOperation

BIND = re.compile(r"binding parameter\s*\((\d+):([^)]*)\)\s*<-\s*\[(.*)\]\s*$")
SQL_LOG = re.compile(r"(?:org\.hibernate\.SQL\s*:\s*|^\s*Hibernate:\s*)(.*)$")
LOG_START = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
NUMBER_TYPES = {'BIGINT', 'INTEGER', 'INT', 'SMALLINT', 'TINYINT', 'NUMERIC', 'DECIMAL', 'FLOAT', 'DOUBLE', 'REAL'}


def literal(kind, value):
    kind = kind.strip().upper()
    if value.lower() == 'null':
        return 'NULL'
    if kind in NUMBER_TYPES:
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError(f'Valor numérico inválido para {kind}: {value}') from None
        if not number.is_finite():
            raise ValueError(f'Valor numérico não finito: {value}')
        return str(number)
    if kind in {'BOOLEAN', 'BOOL', 'BIT'}:
        values = {'true': 'TRUE', 'false': 'FALSE', '1': 'TRUE', '0': 'FALSE'}
        if value.lower() not in values:
            raise ValueError(f'Booleano inválido: {value}')
        return values[value.lower()]
    # E strings preservam barras invertidas independentemente da configuração do banco.
    quoted = "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"
    cast = {'DATE': 'date', 'TIME': 'time', 'TIMESTAMP': 'timestamp',
            'TIMESTAMP_WITH_TIMEZONE': 'timestamptz', 'TIME_WITH_TIMEZONE': 'timetz',
            'UUID': 'uuid'}.get(kind)
    return quoted + ('::' + cast if cast else '')


def substitute(sql, parameters):
    """Percorre SQL sem substituir interrogações em strings, identificadores ou comentários."""
    result = []
    index = 0
    position = 1
    while index < len(sql):
        start = index
        char = sql[index]
        if char in "'\"":
            quote = char
            escaped = quote == "'" and index > 0 and sql[index - 1] in 'eE' and (index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] == '_'))
            index += 1
            while index < len(sql):
                if escaped and sql[index] == '\\':
                    index += 2
                elif sql[index] == quote:
                    index += 1
                    if index < len(sql) and sql[index] == quote:
                        index += 1
                    else:
                        break
                else:
                    index += 1
            else:
                raise ValueError('SQL contém aspas sem fechamento.')
        elif sql.startswith('--', index):
            end = sql.find('\n', index)
            index = len(sql) if end == -1 else end + 1
        elif sql.startswith('/*', index):
            index += 2
            depth = 1
            while index < len(sql) and depth:
                if sql.startswith('/*', index):
                    depth += 1
                    index += 2
                elif sql.startswith('*/', index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError('Comentário SQL sem fechamento.')
        elif char == '$' and (match := re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$', sql[index:])):
            delimiter = match.group()
            end = sql.find(delimiter, index + len(delimiter))
            if end == -1:
                raise ValueError('String SQL com dollar quoting sem fechamento.')
            index = end + len(delimiter)
        elif char == '?':
            if position not in parameters:
                raise ValueError(f'Falta o parâmetro {position}. Cole todos os logs de binding desta query.')
            result.append(parameters[position])
            position += 1
            index += 1
            continue
        else:
            index += 1
        result.append(sql[start:index])
    extras = set(parameters) - set(range(1, position))
    if extras:
        raise ValueError('Há parâmetros excedentes: ' + ', '.join(map(str, sorted(extras))))
    return ''.join(result).strip()


def convert(log):
    if not log.strip():
        raise ValueError('Cole os logs do Hibernate primeiro.')
    queries = []
    current = None
    collecting = False
    for line in log.splitlines():
        if match := SQL_LOG.search(line):
            sql = match.group(1).strip()
            current = {'sql': sql, 'parameters': {}}
            queries.append(current)
            collecting = True
        elif match := BIND.search(line):
            if current is None:
                raise ValueError('Encontrado binding sem uma SQL anterior.')
            position, kind, value = match.groups()
            position = int(position)
            if position < 1 or position in current['parameters']:
                raise ValueError(f'Índice de parâmetro inválido ou repetido: {position}. Separe logs intercalados.')
            current['parameters'][position] = literal(kind, value)
            collecting = False
        elif LOG_START.match(line):
            collecting = False
        elif collecting and line.strip():
            current['sql'] += '\n' + line
        elif current is None and line.strip():
            current = {'sql': line.strip(), 'parameters': {}}
            queries.append(current)
            collecting = True
    if not queries:
        raise ValueError('Nenhuma SQL encontrada nos logs.')
    # Compare blocos completos: a SQL duplicada também pode ocupar várias linhas.
    unique = []
    for query in queries:
        if unique and not unique[-1]['parameters'] and unique[-1]['sql'].strip() == query['sql'].strip():
            unique[-1] = query
        else:
            unique.append(query)
    return [substitute(query['sql'], query['parameters']) for query in unique]

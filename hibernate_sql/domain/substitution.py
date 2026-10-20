import re
from typing import Mapping

from hibernate_sql.domain.models import ParameterError


DOLLAR_DELIMITER = re.compile(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$')


def quoted_end(sql: str, start: int) -> int:
    quote = sql[start]
    escaped = (
        quote == "'" and start > 0 and sql[start - 1] in 'eE'
        and (start < 2 or not (sql[start - 2].isalnum() or sql[start - 2] in '_$'))
    )
    index = start + 1
    while index < len(sql):
        if escaped and sql[index] == '\\':
            index += 2
        elif sql[index] == quote:
            if index + 1 < len(sql) and sql[index + 1] == quote:
                index += 2
            else:
                return index + 1
        else:
            index += 1
    raise ValueError('SQL contém aspas sem fechamento.')


def block_comment_end(sql: str, start: int) -> int:
    index = start + 2
    depth = 1
    while index < len(sql):
        if sql.startswith('/*', index):
            depth += 1
            index += 2
        elif sql.startswith('*/', index):
            depth -= 1
            index += 2
            if depth == 0:
                return index
        else:
            index += 1
    raise ValueError('Comentário SQL sem fechamento.')


def protected_end(sql: str, index: int) -> int:
    if sql[index] in "'\"":
        return quoted_end(sql, index)
    if sql.startswith('--', index):
        end = sql.find('\n', index)
        return len(sql) if end == -1 else end + 1
    if sql.startswith('/*', index):
        return block_comment_end(sql, index)
    if sql[index] == '$' and (
        index == 0 or not (sql[index - 1].isalnum() or sql[index - 1] in '_$')
    ):
        match = DOLLAR_DELIMITER.match(sql, index)
        if match:
            delimiter = match.group()
            end = sql.find(delimiter, match.end())
            if end == -1:
                raise ValueError('String SQL com dollar quoting sem fechamento.')
            return end + len(delimiter)
    return index


def substitute(sql: str, parameters: Mapping[int, str]) -> str:
    result = []
    index = 0
    position = 1
    while index < len(sql):
        end = protected_end(sql, index)
        if end > index:
            result.append(sql[index:end])
            index = end
        elif sql[index] == '?':
            if position not in parameters:
                raise ParameterError(
                    f'Falta o parâmetro {position}. '
                    'Cole todos os logs de binding desta query.', position,
                )
            result.append(parameters[position])
            position += 1
            index += 1
        else:
            result.append(sql[index])
            index += 1
    extras = set(parameters) - set(range(1, position))
    if extras:
        raise ParameterError('Há parâmetros excedentes: ' + ', '.join(map(str, sorted(extras))), min(extras))
    return ''.join(result).strip()

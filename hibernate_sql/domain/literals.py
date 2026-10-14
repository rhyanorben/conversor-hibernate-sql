from decimal import Decimal, InvalidOperation


NUMBER_TYPES = frozenset({
    'BIGINT', 'INTEGER', 'INT', 'SMALLINT', 'TINYINT', 'NUMERIC',
    'DECIMAL', 'FLOAT', 'DOUBLE', 'REAL',
})
BOOLEAN_VALUES = {'true': 'TRUE', 'false': 'FALSE', '1': 'TRUE', '0': 'FALSE'}
TYPE_CASTS = {
    'DATE': 'date',
    'TIME': 'time',
    'TIMESTAMP': 'timestamp',
    'TIMESTAMP_WITH_TIMEZONE': 'timestamptz',
    'TIME_WITH_TIMEZONE': 'timetz',
    'UUID': 'uuid',
}


def numeric_literal(kind: str, value: str) -> str:
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f'Valor numérico inválido para {kind}: {value}') from None
    if not number.is_finite():
        raise ValueError(f'Valor numérico não finito: {value}')
    return str(number)


def literal(kind: str, value: str) -> str:
    normalized_kind = kind.strip().upper()
    normalized_value = value.lower()
    if normalized_value == 'null':
        return 'NULL'
    if normalized_kind in NUMBER_TYPES:
        return numeric_literal(normalized_kind, value)
    if normalized_kind in {'BOOLEAN', 'BOOL', 'BIT'}:
        if normalized_value not in BOOLEAN_VALUES:
            raise ValueError(f'Booleano inválido: {value}')
        return BOOLEAN_VALUES[normalized_value]
    quoted = "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"
    cast = TYPE_CASTS.get(normalized_kind)
    return quoted + ('::' + cast if cast else '')

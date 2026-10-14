from typing import List

from hibernate_sql.application.conversion import ConversionService
from hibernate_sql.domain.literals import literal
from hibernate_sql.domain.substitution import substitute
from hibernate_sql.infrastructure.hibernate_logs import HibernateLogParser

__all__ = ['convert', 'literal', 'substitute']


def convert(log: str) -> List[str]:
    return ConversionService(HibernateLogParser()).convert(log)

from typing import List, Protocol

from hibernate_sql.domain.models import Query


class QueryParser(Protocol):
    def parse(self, log: str) -> List[Query]:
        ...

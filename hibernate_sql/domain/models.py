from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class Binding:
    kind: str
    value: str


@dataclass
class Query:
    sql: str
    parameters: Dict[int, Binding] = field(default_factory=dict)

    def add_binding(self, position: int, binding: Binding) -> None:
        if position < 1 or position in self.parameters:
            raise ValueError(
                f'Índice de parâmetro inválido ou repetido: {position}. '
                'Separe logs intercalados.'
            )
        self.parameters[position] = binding

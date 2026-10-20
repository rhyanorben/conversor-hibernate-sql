from dataclasses import dataclass, field
from typing import Dict, Optional


class ParameterError(ValueError):
    def __init__(self, message: str, position: int):
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class Binding:
    kind: str
    value: str


@dataclass
class Query:
    sql: str
    parameters: Dict[int, Binding] = field(default_factory=dict)
    line_number: Optional[int] = None
    thread: Optional[str] = None
    binding_lines: Dict[int, int] = field(default_factory=dict)

    def error(self, message: str, number: int, parameter=None, line=None) -> ValueError:
        context = [f'Query {number}']
        if self.line_number is not None:
            context.append(f'SQL na linha {self.line_number}')
        if self.thread is not None:
            context.append(f'thread {self.thread}')
        if parameter is not None:
            context.append(f'parâmetro {parameter}')
        if line is not None and line != self.line_number:
            context.append(f'linha {line}')
        return ValueError(', '.join(context) + ': ' + message)

    def add_binding(self, position: int, binding: Binding) -> None:
        if position < 1:
            raise ValueError(
                f'Índice de parâmetro inválido: {position}. As posições começam em 1.'
            )
        if position in self.parameters:
            raise ValueError(
                f'Parâmetro repetido: {position}. '
                'O binding desta posição já foi informado para esta execução.'
            )
        self.parameters[position] = binding

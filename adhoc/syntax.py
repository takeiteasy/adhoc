"""The AST: frozen dataclasses, not an s-expression list.

Mirrors the Rust `ast.rs` design: every node carries its own `Span`, tagged at
construction time by the parser (see `parser.py` for why *at construction* matters for
parenthesized expressions). Nodes are immutable, so quoting and rewriting them (the
phase-4 symbolic-algebra plan) is ordinary match-and-rebuild over these classes.
"""

from dataclasses import dataclass
from enum import Enum, auto

from .span import Span


class BinOperator(Enum):
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    POW = auto()


class UnaryOperator(Enum):
    NEG = auto()


@dataclass(frozen=True)
class Node:
    span: Span


@dataclass(frozen=True)
class NumLit(Node):
    text: str


@dataclass(frozen=True)
class Var(Node):
    ch: str


@dataclass(frozen=True)
class BackslashRef(Node):
    name: str


@dataclass(frozen=True)
class BinOp(Node):
    op: BinOperator
    lhs: Node
    rhs: Node


@dataclass(frozen=True)
class UnOp(Node):
    op: UnaryOperator
    operand: Node


@dataclass(frozen=True)
class Assign(Node):
    name: str
    force: bool
    value: Node


@dataclass(frozen=True)
class Seq(Node):
    statements: tuple[Node, ...]

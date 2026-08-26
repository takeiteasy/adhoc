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


class CompareOperator(Enum):
    LT = auto()
    LE = auto()
    GT = auto()
    GE = auto()


class UnaryOperator(Enum):
    NEG = auto()


@dataclass(frozen=True)
class Node:
    span: Span


@dataclass(frozen=True)
class NumLit(Node):
    text: str


@dataclass(frozen=True)
class StrLit(Node):
    """A string literal. Strings are not values (docs/grammar.md): a StrLit only ever
    appears as a whole statement (ignored, comment-like) or as an argument of a call,
    where it converts to a native Python str at the boundary and never becomes an ad
    value."""

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
class Compare(Node):
    op: CompareOperator
    lhs: Node
    rhs: Node


@dataclass(frozen=True)
class Range(Node):
    """An inclusive finite or lazy infinite arithmetic progression."""

    start: Node
    second: Node | None
    end: Node | None


@dataclass(frozen=True)
class IfExpr(Node):
    condition: Node
    then_branch: Node
    otherwise: Node | None


@dataclass(frozen=True)
class Fold(Node):
    """`\\sum`/`\\prod` (≡ `Σ`/`Π`): bind a loop variable over a range and fold
    ADD/MUL over the body. The bound variable scopes like a function parameter:
    reads of other names fall through to globals, writes stay local."""

    op: BinOperator
    var: str
    rng: Range
    body: Node


@dataclass(frozen=True)
class Limit(Node):
    """`\\lim(x=a) f(x)` — numeric only: approximate the limiting value of the body
    as `var` approaches the point, sharing the tolerance/convergence mechanism with
    infinite-range folds."""

    var: str
    point: Node
    body: Node


@dataclass(frozen=True)
class Call(Node):
    """Postfix application `head(arg, ...)`. The syntactic rule: a trailer `(…)`
    attaches only to name-ish heads (Var/BackslashRef) or to another Call —
    number-headed parens stay juxtaposition (`2(x+1)` is still `2*(x+1)`). Whether the
    call applies or falls back to multiplication is decided at evaluation."""

    head: Node
    args: tuple[Node, ...]


@dataclass(frozen=True)
class FuncDef(Node):
    """A function definition with a semicolon-sequenced body."""

    name: str
    params: tuple[str, ...]
    force: bool
    body: Node


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

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
    """A string literal: a full ad value (docs/grammar.md). Appears as a whole
    statement (echoes nothing, comment-like), as a call argument, or anywhere an
    expression is — `+` concatenates, every other operator rejects it as the usual
    typed "strings are not numbers"."""

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
    """A lazy conditional: only the selected branch evaluates. The ternary
    `c ? a : b` is the one conditional — the branches may be any expression,
    including parenthesized statement groups (`docs/grammar.md`)."""

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
class KwArg(Node):
    """A `name=value` argument inside a call's argument list. Names are single-character
    identifiers or `\\`-sigiled multi-character names (`\\dpi`); the value may be any
    expression or a string literal (`\\mode="w"`). KwArgs pass through application to
    Python callables as native keyword arguments; user-defined functions reject them."""

    name: str
    value: Node


@dataclass(frozen=True)
class Call(Node):
    """Postfix application `head(arg, ...)`. The syntactic rule: a trailer `(…)`
    attaches only to name-ish heads (Var/BackslashRef) or to another Call —
    number-headed parens stay juxtaposition (`2(x+1)` is still `2*(x+1)`). Whether the
    call applies or falls back to multiplication is decided at evaluation. Positional
    args and kwargs are collected separately, so their relative source order carries no
    meaning — Python's own binding rules decide what `f(2, \\a=1)` means."""

    head: Node
    args: tuple[Node, ...]
    kwargs: tuple[KwArg, ...] = ()


@dataclass(frozen=True)
class FuncDef(Node):
    """A function definition with a semicolon-sequenced body. Definitions are
    declarations: a protected or already-visible name is an error — nothing ever
    redefines, and identity comparison would make a check meaningless anyway."""

    name: str
    params: tuple[str, ...]
    body: Node


@dataclass(frozen=True)
class UnOp(Node):
    op: UnaryOperator
    operand: Node


@dataclass(frozen=True)
class Lambda(Node):
    """An anonymous function literal, `\\λ(params) body` (ASCII spelling `\\fn`).
    Exactly a definition without the name: eager, fixed arity, the body evaluates in
    a fresh frame over a closure of the defining scope, and there is no self-name to
    recurse through. The body extends greedily over the rest of the current
    expression — a parenthesized group gives it an explicit extent
    (docs/grammar.md)."""

    params: tuple[str, ...]
    body: Node


@dataclass(frozen=True)
class Assign(Node):
    """Statement-level `x = e` — declare-once-then-check. Binds a fresh name into
    the current frame; a name already bound in that frame compares by value and
    prints `true`/`false`; a protected prelude name is rejected (`i` excepted —
    the one shadowable prelude name). Reads walk the
    chain, binds and compares stay frame-local — nothing ever rebinds an existing
    binding, so `x = 1; x = 1` is `true`, never an overwrite."""

    name: str
    value: Node


@dataclass(frozen=True)
class Seq(Node):
    statements: tuple[Node, ...]


@dataclass(frozen=True)
class NoOp(Node):
    """A statement that binds no name and produces no value: the parse-time
    directive statements (`\\alias`, `\\dual`'s declaration half is folded into its
    definition node). Lowers to `pass` exactly like a lone string statement."""


@dataclass(frozen=True)
class Import(Node):
    """`\\import("lib")` / `\\import("lib": f, \\fact)` — statement-level: evaluate an
    ad source file once per session in a fresh root environment and bind its top-level
    names into the importing environment (all of them, or only the listed members).
    Imported functions keep the module's environment as their closure, so their reads
    of module globals stay live. Imports produce no output; an import is a statement,
    never an expression."""

    path: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class PyImport(Node):
    """`\\pyimport("math": \\sqrt, \\tau)` — statement-level: resolve a Python module
    and bind the named members into the importing environment. Callable members bind
    as callables (the `\\py` rule); every other member converts through the interop
    matrix or fails at the import's span. Member selection is mandatory — there is no
    module value to bind, and dotted attribute access does not exist in the grammar."""

    path: str
    members: tuple[str, ...]

"""Non-enumerating scalar solution sets (docs/symbolic.md)."""

from dataclasses import dataclass, field
from itertools import count

import sympy

from .span import Span
from . import units
from .syntax import Node


_SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_DOMAINS = {sympy.S.Integers: ("ℤ", r"\mathbb{Z}"),
            sympy.S.Reals: ("ℝ", r"\mathbb{R}"),
            sympy.S.Complexes: ("ℂ", r"\mathbb{C}"),
            sympy.S.Naturals: ("ℕ", r"\mathbb{N}"),
            sympy.S.Naturals0: ("ℕ₀", r"\mathbb{N}_0")}
_SET_OPERATORS = {sympy.Union: (" ∪ ", r" \cup "),
                  sympy.Intersection: (" ∩ ", r" \cap "),
                  sympy.Complement: (" ∖ ", r" \setminus ")}


@dataclass(frozen=True, eq=False)
class SymbolicSetValue:
    expr: sympy.Set
    names: tuple[tuple[sympy.Symbol, Node], ...] = field(default=(), compare=False)
    dimensions: tuple = units.DIMENSIONLESS
    __hash__ = None

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, SymbolicSetValue)
                and self.dimensions == other.dimensions
                and self.expr.as_dummy() == other.expr.as_dummy())

    def contains(self, value) -> bool:
        from .rewrite import RewriteError, run_limited
        from .runtime import NumError, _NUMERIC_TYPES, value_to_sympy
        if isinstance(value, bool) or not isinstance(value, _NUMERIC_TYPES):
            raise NumError("symbolic set membership needs a number")
        magnitude, dimension = units.parts(value)
        if dimension != self.dimensions:
            return False
        try:
            return run_limited(_contains, self.expr, value_to_sympy(magnitude))
        except RewriteError as error:
            raise NumError(f"symbolic set membership {error}") from None

    def render(self, *, tex: bool = False) -> str:
        from .expression import show
        from .rewrite import Bridge, RewriteError
        from .tex import node_tex
        bridge = Bridge(Span(0, 0), nodes=dict(self.names))

        def scalar(expr):
            try:
                from .dimensional import restore
                node = restore(expr, bridge, self.dimensions)
            except RewriteError:
                return sympy.latex(expr) if tex else str(expr)
            return node_tex(node) if tex else show(node)

        def render(expr):
            if expr in _DOMAINS:
                domain = _DOMAINS[expr][tex]
                if self.dimensions == units.DIMENSIONLESS:
                    return domain
                suffix = units.unit_text(self.dimensions)
                if tex:
                    from .dimensional import unit_node
                    suffix = node_tex(unit_node(self.dimensions, Span(0, 0)))
                return domain + (r"\, " if tex else "*") + suffix
            if expr is sympy.S.EmptySet:
                return r"\emptyset" if tex else "{}"
            if isinstance(expr, sympy.ImageSet):
                used = {symbol.name for symbol in self.expr.free_symbols}
                variables = []
                for _ in expr.lamda.variables:
                    for suffix in count():
                        name = "n" + (str(suffix).translate(_SUBSCRIPTS) if suffix else "")
                        if name not in used:
                            break
                    used.add(name)
                    variables.append(sympy.Symbol(name))
                body = expr.lamda.expr.xreplace(dict(zip(expr.lamda.variables, variables)))
                binders = [(node_tex(bridge.to_node(variable)) if tex else show(bridge.to_node(variable)),
                            _DOMAINS[base][tex] if base in _DOMAINS else render(base))
                           for variable, base in zip(variables, expr.base_sets)]
                member = r"\in" if tex else "∈"
                tail = ", ".join(f"{name} {member} {base}" for name, base in binders)
                return (rf"\{{ {scalar(body)} \mid {tail} \}}" if tex
                        else f"{{{scalar(body)} | {tail}}}")
            if isinstance(expr, sympy.Union | sympy.Intersection | sympy.Complement):
                parts = [render(part) for part in expr.args]
                text = _SET_OPERATORS[type(expr)][tex].join(parts)
                return rf"\left({text}\right)" if tex else f"({text})"
            if isinstance(expr, sympy.FiniteSet):
                text = ", ".join(scalar(item) for item in sorted(expr, key=sympy.default_sort_key))
                return rf"\{{{text}\}}" if tex else "{" + text + "}"
            return sympy.latex(expr) if tex else str(expr)

        return render(self.expr)


def _contains(collection: sympy.Set, value: sympy.Expr) -> bool:
    from .rewrite import RewriteError
    result = sympy.simplify(collection.contains(value))
    if result is sympy.S.true:
        return True
    if result is sympy.S.false:
        return False
    raise RewriteError("cannot determine membership")

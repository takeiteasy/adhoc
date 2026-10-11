"""Symbolic rewriting over expression values: `\\simplify`, `\\expand`, `\\factor`, `\\solve`
(docs/symbolic.md).

An expression quote or a user function's body crosses to sympy, sympy rewrites it, and the
result crosses back as an expression quote. Free names stay symbols; a function's closure
supplies its numeric bindings. Only the numeric seam converts ad values to sympy
(`runtime.value_to_sympy`)."""

import multiprocessing
import os
import pickle
import warnings
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

import sympy

from .expression import ExpressionValue
from .tensor import ArrayValue
from .span import Span
from .syntax import (
    BackslashRef, BinOp, BinOperator, Call, Equation, Node, NumLit, PowCall, Seq, UnaryOperator, UnOp,
    Var, is_short_name,
)


class RewriteError(Exception):
    pass


DEFAULT_TIMEOUT = 5.0
_IN_WORKER = False


def _timeout_seconds() -> float:
    text = os.environ.get("ADHOC_SYMBOLIC_TIMEOUT")
    if text is None:
        return DEFAULT_TIMEOUT
    try:
        return float(text)
    except ValueError:
        raise RewriteError(f"needs ADHOC_SYMBOLIC_TIMEOUT to be a number of seconds, got {text!r}") from None


def _child(send: Any, fn: Callable, args: tuple) -> None:
    global _IN_WORKER
    _IN_WORKER = True
    try:
        payload = ("ok", fn(*args))
    except BaseException as error:
        payload = ("error", error)
    try:
        pickle.dumps(payload)
    except Exception:
        payload = ("error", RewriteError("returned a result that cannot be sent back"))
    send.send(payload)


def run_limited(fn: Callable, *args: Any) -> Any:
    """`fn(*args)` in a forked child that is killed after the time limit; the result comes
    back pickled. Nested work shares the worker's deadline. Unlimited without `fork`."""
    seconds = _timeout_seconds()
    if seconds <= 0 or _IN_WORKER or "fork" not in multiprocessing.get_all_start_methods():
        return fn(*args)
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(target=_child, args=(send, fn, args), daemon=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # fork from a threaded process
        child.start()
    send.close()
    try:
        if not receive.poll(seconds):
            raise RewriteError(f"took longer than {seconds:g}s")
        try:
            status, payload = receive.recv()
        except EOFError:
            raise RewriteError("stopped unexpectedly") from None
    finally:
        child.kill()
        child.join()
        receive.close()
    if status == "error":
        raise payload
    return payload


def _function_operation(operation):
    @wraps(operation)
    def limited(value, *args, **kwargs):
        from .runtime import AdFunction
        inputs = value.items if isinstance(value, ArrayValue) else (value,)
        if any(isinstance(item, AdFunction) for item in inputs):
            return run_limited(_apply_operation, operation, value, args, kwargs)
        return operation(value, *args, **kwargs)
    return limited


def _apply_operation(operation, value, args, kwargs):
    return operation(value, *args, **kwargs)


_FUNCTIONS = {
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan, "asin": sympy.asin,
    "acos": sympy.acos, "atan": sympy.atan, "sinh": sympy.sinh, "cosh": sympy.cosh,
    "tanh": sympy.tanh, "asinh": sympy.asinh, "acosh": sympy.acosh, "atanh": sympy.atanh,
    "exp": sympy.exp, "ln": sympy.log, "sqrt": sympy.sqrt, "abs": sympy.Abs,
}
_NAMES = {sympy.sin: "sin", sympy.cos: "cos", sympy.tan: "tan", sympy.asin: "asin",
          sympy.acos: "acos", sympy.atan: "atan", sympy.sinh: "sinh", sympy.cosh: "cosh",
          sympy.tanh: "tanh", sympy.asinh: "asinh", sympy.acosh: "acosh",
          sympy.atanh: "atanh", sympy.exp: "exp", sympy.log: "ln", sympy.Abs: "abs"}
_CONSTANTS = {"pi": sympy.pi, "e": sympy.E, "i": sympy.I, "inf": sympy.oo}


@dataclass
class Bridge:
    """One rewrite's name table: which names are symbols, and how symbols map back to the
    source nodes that spelled them."""

    span: Span
    bound: frozenset[str] = frozenset()
    lookup: Callable[[str], Any] | None = None
    nodes: dict[sympy.Symbol, Node] = field(default_factory=dict)
    call_lookup: Callable[[str], Any] | None = None
    active: tuple[Any, ...] = ()

    def symbol(self, name: str, node: Node) -> sympy.Symbol:
        symbol = sympy.Symbol(name)
        self.nodes.setdefault(symbol, node)
        return symbol

    def name(self, node: Var | BackslashRef) -> sympy.Expr:
        name = node.ch if isinstance(node, Var) else node.name
        if name not in self.bound:
            if self.lookup is not None:
                bound = self.lookup(name)
                if bound is not None:
                    return bound
            if name in _CONSTANTS:
                return _CONSTANTS[name]
        return self.symbol(name, node)

    def to_sympy(self, node: Node) -> sympy.Expr:
        if isinstance(node, Call) and isinstance(node.head, Var | BackslashRef):
            label = node.head.ch if isinstance(node.head, Var) else node.head.name
            if self.call_lookup is not None and label not in self.bound:
                from .runtime import AdFunction, _MISSING
                fn = self.call_lookup(label)
                if isinstance(fn, AdFunction):
                    if node.kwargs or len(node.args) != len(fn.params):
                        raise RewriteError(f"{label} needs {len(fn.params)} positional arguments")
                    from .dimensional import has_units
                    if has_units(fn.body.node, fn.closure._lookup):
                        raise RewriteError("nested dimensioned function calls are unsupported")
                    arguments = tuple(self.to_sympy(arg) for arg in node.args)
                    origin = _bridge_function(fn, active=self.active)
                    replacements = dict(zip(origin.params, (sympy.Dummy(p.name) for p in origin.params)))
                    body = origin.expr.xreplace(replacements)
                    return body.xreplace(dict(zip(replacements.values(), arguments)))
                if fn is not _MISSING and not callable(fn) and len(node.args) == 1 and not node.kwargs:
                    return self.name(node.head) * self.to_sympy(node.args[0])
        match node:
            case NumLit(text=text):
                from .runtime import parse_literal, value_to_sympy
                return value_to_sympy(parse_literal(text))
            case Var() | BackslashRef():
                return self.name(node)
            case UnOp(op=UnaryOperator.NEG, operand=operand):
                return -self.to_sympy(operand)
            case BinOp(op=op, lhs=lhs, rhs=rhs) if op in _ARITHMETIC:
                return _ARITHMETIC[op](self.to_sympy(lhs), self.to_sympy(rhs))
            case PowCall(head=head, exponent=exponent, args=args, kwargs=()) if not (
                    isinstance(exponent, UnOp) and exponent.op is UnaryOperator.NEG):
                return self.to_sympy(Call(head=head, args=args, span=node.span)) \
                    ** self.to_sympy(exponent)
            case Call(head=BackslashRef(name="log"), args=(value,)):
                return sympy.log(self.to_sympy(value))
            case Call(head=BackslashRef(name="log"), args=(base, value)):
                return sympy.log(self.to_sympy(value), self.to_sympy(base))
            case Call(head=BackslashRef(name="root"), args=(value, index)):
                return sympy.root(self.to_sympy(value), self.to_sympy(index))
            case Call(head=BackslashRef(name=name), args=(arg,)) if name in _FUNCTIONS:
                return _FUNCTIONS[name](self.to_sympy(arg))
            case Call(head=Var() | BackslashRef() as head, args=args, kwargs=()):
                label = head.ch if isinstance(head, Var) else head.name
                return sympy.Function(label)(*(self.to_sympy(a) for a in args))
        raise RewriteError(f"cannot rewrite {_describe(node)}")

    def _atom(self, expr: sympy.Expr) -> Node:
        span = self.span
        if expr in self.nodes:
            return self.nodes[expr]
        if expr.is_Integer:
            text = str(abs(int(expr)))
            node: Node = NumLit(text=text, span=span)
            return UnOp(op=UnaryOperator.NEG, operand=node, span=span) if expr < 0 else node
        if expr.is_Rational:
            ratio = BinOp(op=BinOperator.DIV, lhs=NumLit(text=str(abs(expr.p)), span=span),
                          rhs=NumLit(text=str(expr.q), span=span), span=span)
            return UnOp(op=UnaryOperator.NEG, operand=ratio, span=span) if expr < 0 else ratio
        if expr.is_Float:
            text = repr(abs(float(expr)))
            node = NumLit(text=text if "e" in text else text + "e0", span=span)
            return UnOp(op=UnaryOperator.NEG, operand=node, span=span) if expr < 0 else node
        if expr is sympy.pi:
            return BackslashRef(name="pi", span=span, spelling="\\pi")
        if expr is sympy.E:
            return Var(ch="e", span=span, spelling="e")
        if expr is sympy.I:
            return Var(ch="i", span=span, spelling="i")
        if expr is sympy.oo:
            return BackslashRef(name="inf", span=span, spelling="\\inf")
        if isinstance(expr, sympy.Symbol):
            name = expr.name
            if is_short_name(name):
                return Var(ch=name, span=span, spelling=name)
            return BackslashRef(name=name, span=span, spelling=f"\\{name}")
        raise RewriteError(f"cannot express {expr} as an expression")

    def _call(self, name: str, *args: Node) -> Node:
        return Call(head=BackslashRef(name=name, span=self.span, spelling=f"\\{name}"),
                    args=args, span=self.span)

    def _binary(self, op: BinOperator, lhs: Node, rhs: Node) -> Node:
        return BinOp(op=op, lhs=lhs, rhs=rhs, span=self.span)

    def to_node(self, expr: sympy.Expr) -> Node:
        if expr.is_Atom:
            return self._atom(expr)
        if expr.is_Add:
            terms = expr.as_ordered_terms()
            node = self.to_node(terms[0])
            for term in terms[1:]:
                if term.could_extract_minus_sign():
                    node = self._binary(BinOperator.SUB, node, self.to_node(-term))
                else:
                    node = self._binary(BinOperator.ADD, node, self.to_node(term))
            return node
        if expr.is_Mul:
            if expr.could_extract_minus_sign():
                return UnOp(op=UnaryOperator.NEG, operand=self.to_node(-expr), span=self.span)
            numer, denom = sympy.fraction(expr)
            if denom != 1:
                return self._binary(BinOperator.DIV, self.to_node(numer), self.to_node(denom))
            factors = sympy.Mul.make_args(expr)
            node = self.to_node(factors[0])
            for factor in factors[1:]:
                node = self._binary(BinOperator.MUL, node, self.to_node(factor))
            return node
        if expr.is_Pow:
            base, exponent = expr.args
            if exponent == sympy.Rational(1, 2):
                return self._call("sqrt", self.to_node(base))
            if exponent.is_negative:
                return self._binary(BinOperator.DIV, NumLit(text="1", span=self.span),
                                    self.to_node(base ** -exponent))
            return self._binary(BinOperator.POW, self.to_node(base), self.to_node(exponent))
        if isinstance(expr, sympy.Function):
            if expr.func in _NAMES:
                return self._call(_NAMES[expr.func], *(self.to_node(a) for a in expr.args))
            if isinstance(expr.func, sympy.core.function.UndefinedFunction):
                symbol = self.nodes.get(sympy.Symbol(expr.func.__name__))
                head = symbol or self._atom(sympy.Symbol(expr.func.__name__))
                return Call(head=head, args=tuple(self.to_node(a) for a in expr.args),
                            span=self.span)
        raise RewriteError(f"cannot express {expr} as an expression")


_ARITHMETIC = {
    BinOperator.ADD: lambda a, b: a + b, BinOperator.SUB: lambda a, b: a - b,
    BinOperator.MUL: lambda a, b: a * b, BinOperator.DIV: lambda a, b: a / b,
    BinOperator.POW: lambda a, b: a ** b,
}


def _describe(node: Node) -> str:
    return type(node).__name__.lower() + " expressions"


@dataclass
class Source:
    """What a rewrite starts from: the sympy expression, its bridge, the quote's source
    text, and the parameter symbols when it came from a function."""

    expr: sympy.Expr
    bridge: Bridge
    source: str
    params: tuple[sympy.Symbol, ...] = ()


def _single_expression(node: Node) -> Node:
    if isinstance(node, Seq):
        if len(node.statements) != 1:
            raise RewriteError("cannot rewrite a function with several statements")
        node = node.statements[0]
    return node


def bridge_function(fn: Any, declared=None) -> Source:
    return run_limited(_function_source, fn, declared)


def _function_source(fn: Any, declared=None) -> Source:
    origin = _bridge_function(fn, declared)
    origin.bridge.lookup = None
    origin.bridge.call_lookup = None
    origin.bridge.active = ()
    return origin


def _bridge_function(fn: Any, declared=None, active=()) -> Source:
    if any(fn is caller for caller in active):
        raise RewriteError("cannot rewrite recursive function calls")
    node = _single_expression(fn.body.node)
    from . import dimensional
    from .runtime import _MISSING
    def lookup(name):
        value = fn.closure._lookup(name)
        return None if value is _MISSING else value
    bridge = dimensional.bridge(node, declared=declared, bound=frozenset(fn.params), lookup=lookup)
    bridge = bridge or Bridge(node.span, frozenset(fn.params), _closure_lookup(fn.closure))
    bridge.call_lookup = lambda name: fn if name == fn.name else fn.closure._lookup(name)
    bridge.active = (*active, fn)
    for param in fn.params:
        bridge.symbol(param, Var(ch=param, span=node.span, spelling=param)
                      if is_short_name(param) else
                      BackslashRef(name=param, span=node.span, spelling=f"\\{param}"))
    expr = bridge.to_sympy(node)
    return Source(expr, bridge, fn.body.source, tuple(sympy.Symbol(p) for p in fn.params))


def _closure_lookup(closure: Any) -> Callable[[str], Any]:
    def lookup(name: str) -> Any:
        from .runtime import _MISSING, value_to_sympy, NumError
        value = closure._lookup(name)
        if value is _MISSING:
            return None
        try:
            return value_to_sympy(value)
        except NumError:
            return None
    return lookup


def bridge_value(value: Any, declared=None) -> Source:
    from .runtime import AdFunction
    if isinstance(value, AdFunction):
        return bridge_function(value, declared)
    if isinstance(value, ExpressionValue):
        if value.statement_body:
            raise RewriteError("needs an expression quote, not a statement quote")
        from . import dimensional
        bridge = dimensional.bridge(value.node, value, declared) or Bridge(value.node.span)
        return Source(bridge.to_sympy(value.node), bridge, value.source)
    raise RewriteError("needs an expression quote or a user-defined function")


def _bridge_equation(value: Any, declared=None) -> Source:
    if (isinstance(value, ExpressionValue) and not value.statement_body
            and isinstance(value.node, Equation)):
        from . import dimensional
        bridge = dimensional.bridge(value.node, value, declared)
        if bridge is not None:
            expr = bridge.to_sympy(value.node)
        else:
            bridge = Bridge(value.node.span)
            expr = bridge.to_sympy(value.node.lhs) - bridge.to_sympy(value.node.rhs)
        return Source(expr, bridge, value.source)
    return bridge_value(value, declared)


def quote(expr: sympy.Expr, bridge: Bridge, source: str, dims=None) -> ExpressionValue:
    from .dimensional import DimensionBridge, restore
    if isinstance(bridge, DimensionBridge):
        node = restore(expr, bridge, bridge.result_dimensions if dims is None else dims)
        return ExpressionValue(node, source, dimensions=bridge.metadata)
    return ExpressionValue(bridge.to_node(expr), source)


@_function_operation
def rewrite(value: Any, operation: Callable[[sympy.Expr], sympy.Expr], *, dimensions=None) -> ExpressionValue:
    from . import dimensional
    declared = dimensional.annotations(dimensions) if dimensions is not None else None
    if (isinstance(value, ExpressionValue) and not value.statement_body
            and isinstance(value.node, Equation)):
        equation = value.node
        checked = dimensional.bridge(equation, value, declared)
        if checked is not None:
            checked.to_sympy(equation)
            lhs, ld = checked.measure(equation.lhs)
            rhs, rd = checked.measure(equation.rhs)
            lhs, rhs = run_limited(_rewrite_sides, operation, lhs, rhs)
            node = Equation(lhs=dimensional.restore(lhs, checked, ld),
                            rhs=dimensional.restore(rhs, checked, rd), span=equation.span)
            return ExpressionValue(node, value.source, dimensions=checked.metadata)
        left, right = Bridge(equation.lhs.span), Bridge(equation.rhs.span)
        lhs, rhs = left.to_sympy(equation.lhs), right.to_sympy(equation.rhs)
        lhs, rhs = run_limited(_rewrite_sides, operation, lhs, rhs)
        node = Equation(lhs=left.to_node(lhs), rhs=right.to_node(rhs), span=equation.span)
        return ExpressionValue(node, value.source)
    origin = bridge_value(value, declared)
    result = run_limited(operation, origin.expr)
    return quote(result, origin.bridge, origin.source)


def _rewrite_sides(operation: Callable, lhs: sympy.Expr,
                   rhs: sympy.Expr) -> tuple[sympy.Expr, sympy.Expr]:
    return operation(lhs), operation(rhs)


@_function_operation
def derivative(value: Any, unknown: Any = None, order: Any = 1, *, dimensions=None) -> Any:
    """The exact derivative: one quote for a single unknown or a list of them (a mixed
    partial), the gradient (an array of quotes) when several names are candidates."""
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise RewriteError("needs the order to be a positive integer")
    from .dimensional import annotations
    origin = bridge_value(value, annotations(dimensions) if dimensions is not None else None)
    if isinstance(unknown, ArrayValue):
        if order != 1:
            raise RewriteError("takes an order only with a single unknown")
        return _diff(origin, _listed(unknown))
    if unknown is None:
        names = _candidates(origin)
        if len(names) > 1:
            if order != 1:
                raise RewriteError("takes an order only with a single unknown")
            return _gradient(origin, names)
    return _diff(origin, [_unknown(origin, unknown)] * order)


@_function_operation
def gradient(value: Any, unknown: Any = None, *, dimensions=None) -> Any:
    """The array of first partials over the listed names, or over every candidate."""
    from .dimensional import annotations
    origin = bridge_value(value, annotations(dimensions) if dimensions is not None else None)
    if unknown is None:
        return _gradient(origin, _candidates(origin))
    if not isinstance(unknown, ArrayValue):
        raise RewriteError("the unknowns must be an array of quoted names, like ⟨`(x), `(y)⟩")
    return _gradient(origin, _listed(unknown))


def _diff(origin: Source, symbols: list[sympy.Symbol]) -> ExpressionValue:
    result = run_limited(sympy.diff, origin.expr, *symbols)
    from .dimensional import DimensionBridge
    from . import units
    dims = None
    if isinstance(origin.bridge, DimensionBridge):
        dims = origin.bridge.result_dimensions
        for symbol in symbols:
            if symbol.name not in origin.bridge.declared:
                raise RewriteError(f"missing dimension annotation for {symbol.name}")
            dims = units.combine(dims, origin.bridge.declared[symbol.name], -1)
    return quote(result, origin.bridge, origin.source, dims)


def _gradient(origin: Source, symbols: list[sympy.Symbol]) -> ArrayValue:
    return ArrayValue(tuple(_diff(origin, [symbol]) for symbol in symbols))


def _listed(unknowns: ArrayValue) -> list[sympy.Symbol]:
    if not unknowns.items:
        raise RewriteError("needs at least one unknown in the array")
    return [_quoted_name(item) for item in unknowns.items]


def _candidates(origin: Source) -> list[sympy.Symbol]:
    """The names to differentiate over when none is given: a function's parameters, else
    the free names in order."""
    if origin.params:
        return list(origin.params)
    names = sorted(origin.expr.free_symbols, key=lambda s: s.name)
    if not names:
        raise RewriteError("has no unknown")
    return names


@_function_operation
def solve(value: Any, unknown: Any = None, *, domain: str = "complex", dimensions=None) -> Any:
    """Solve an equation or `value = 0` in the selected domain, as an ad set."""
    from . import dimensional, units
    declared = dimensional.annotations(dimensions) if dimensions is not None else None
    if not isinstance(domain, str) or domain not in ("complex", "real"):
        raise RewriteError('needs domain="complex" or domain="real"')
    if isinstance(value, ArrayValue) or isinstance(unknown, ArrayValue):
        return _solve_system(value, unknown, domain, declared)
    origin = _bridge_equation(value, declared)
    symbol = _unknown(origin, unknown)
    solution_dims = units.DIMENSIONLESS
    if isinstance(origin.bridge, dimensional.DimensionBridge):
        if symbol.name not in origin.bridge.declared:
            raise RewriteError(f"missing dimension annotation for {symbol.name}")
        solution_dims = origin.bridge.declared[symbol.name]
    solutions = run_limited(sympy.solveset, origin.expr, symbol,
                            sympy.S.Reals if domain == "real" else sympy.S.Complexes)
    return _solution_set(solutions, origin, solution_dims)


def preimages(fn: Any, target: Any, domain: str = "complex") -> Any:
    if not isinstance(domain, str) or domain not in ("complex", "real"):
        raise RewriteError('needs domain="complex" or domain="real"')
    origin, solutions = run_limited(_preimages, fn, target, domain)
    return _solution_set(solutions, origin)


def _preimages(fn: Any, target: Any, domain: str) -> tuple[Source, sympy.Set]:
    from .runtime import AdFunction, PRELUDE, PreludeFn, value_to_sympy
    from .dimensional import has_units
    point = value_to_sympy(target)
    if point.is_finite is False:
        raise RewriteError("needs a finite numeric target")
    if isinstance(fn, AdFunction) and len(fn.params) == 1:
        if has_units(fn.body.node, fn.closure._lookup):
            raise RewriteError("dimensioned inverse functions are unsupported")
        origin = _function_source(fn)
    elif isinstance(fn, PreludeFn) and fn is PRELUDE.get(fn.name) and fn.name in (*_FUNCTIONS, "log"):
        symbol = sympy.Dummy("x")
        operation = sympy.log if fn.name == "log" else _FUNCTIONS[fn.name]
        origin = Source(operation(symbol), Bridge(Span(0, 0)), "", (symbol,))
    else:
        raise RewriteError("all branches need a one-parameter user function or supported elementary prelude function")
    try:
        solutions = sympy.solveset(origin.expr - point, origin.params[0],
                                  sympy.S.Reals if domain == "real" else sympy.S.Complexes)
    except (NotImplementedError, ValueError, sympy.PolynomialError) as error:
        raise RewriteError("cannot solve this equation in closed form") from error
    return origin, solutions


def _solution_set(solutions: sympy.Set, origin: Source, solution_dims=None) -> Any:
    from . import units
    from .runtime import SetValue, _dedup
    from .solution_set import SymbolicSetValue
    solution_dims = units.DIMENSIONLESS if solution_dims is None else solution_dims
    if solutions is sympy.S.EmptySet:
        return SetValue(())
    if not isinstance(solutions, sympy.FiniteSet):
        if not isinstance(solutions, sympy.Set) or solutions.has(sympy.ConditionSet):
            raise RewriteError("cannot solve this equation in closed form")
        return SymbolicSetValue(solutions, tuple(origin.bridge.nodes.items()), solution_dims)
    items = []
    for solution in sorted(solutions, key=sympy.default_sort_key):
        items.append(_solution_value(solution, origin.bridge, origin.source, solution_dims))
    return SetValue(_dedup(items))


def _solution_value(solution: sympy.Expr, bridge: Bridge, source: str, dims=None) -> Any:
    from .runtime import NumError, _sympy_to_ad
    if not solution.free_symbols:
        try:
            from . import units
            return units.attach(_sympy_to_ad(solution, "sympy expression"),
                                units.DIMENSIONLESS if dims is None else dims)
        except NumError:
            pass
    return quote(solution, bridge, source, dims)


def _solve_system(value: Any, unknowns: Any, domain: str, declared=None) -> Any:
    from .expression import show
    from .parser import parse_program
    from .runtime import SetValue, _dedup
    if not isinstance(unknowns, ArrayValue):
        raise RewriteError("systems need an array of quoted unknowns, like ⟨`(x), `(y)⟩")
    symbols = _listed(unknowns)
    if len(set(symbols)) != len(symbols):
        raise RewriteError("needs distinct unknowns in the array")
    values = value.items if isinstance(value, ArrayValue) else (value,)
    if not values:
        raise RewriteError("needs at least one equation in the array")
    from . import dimensional, units
    origins = [_bridge_equation(item, declared) for item in values]
    equations = [origin.expr for origin in origins]
    solutions = run_limited(_system_solutions, equations, symbols, domain)
    checked = next((origin.bridge for origin in origins if isinstance(origin.bridge, dimensional.DimensionBridge)), None)
    bridge = checked or Bridge(Span(0, 0))
    if checked:
        for origin in origins:
            bridge.nodes.update(origin.bridge.nodes)
        for symbol in symbols:
            if symbol.name not in bridge.declared:
                raise RewriteError(f"missing dimension annotation for {symbol.name}")
    items = []
    for row in solutions:
        coordinates = []
        for symbol, solution in zip(symbols, row):
            dims = bridge.declared[symbol.name] if checked else units.DIMENSIONLESS
            coordinate = _solution_value(solution, bridge, "", dims)
            if isinstance(coordinate, ExpressionValue):
                source = show(coordinate.node)
                coordinate = ExpressionValue(_single_expression(parse_program(source)), source,
                                             dimensions=coordinate.dimensions)
            coordinates.append(coordinate)
        items.append(ArrayValue(tuple(coordinates)))
    return SetValue(_dedup(items))


def _system_solutions(equations: list[sympy.Expr], symbols: list[sympy.Symbol],
                      domain: str = "complex") -> list:
    from sympy.solvers.solveset import NonlinearError
    try:
        try:
            matrix, rhs = sympy.linear_eq_to_matrix(equations, symbols)
        except NonlinearError:
            solutions = sympy.nonlinsolve(equations, symbols)
        else:
            solutions = sympy.linsolve((matrix, rhs), symbols)
    except (NotImplementedError, ValueError, KeyError, sympy.PolynomialError) as error:
        raise RewriteError("cannot solve this system in closed form") from error
    if solutions is sympy.S.EmptySet:
        return []
    if not isinstance(solutions, sympy.FiniteSet):
        if isinstance(solutions, sympy.Set) and solutions.is_finite_set is False:
            raise RewriteError("has infinitely many solutions")
        raise RewriteError("cannot solve this system in closed form")
    selected = set(symbols)
    parameters = set().union(*(equation.free_symbols for equation in equations)) - selected
    accepted = []
    for row in sorted(solutions, key=sympy.default_sort_key):
        if not isinstance(row, sympy.Tuple) or len(row) != len(symbols):
            raise RewriteError("cannot solve this system in closed form")
        if any(not isinstance(item, sympy.Expr) for item in row):
            if any(item.has(sympy.ConditionSet) for item in row):
                raise RewriteError("cannot solve this system in closed form")
            raise RewriteError("has infinitely many solutions")
        residuals = [sympy.simplify(equation.subs(dict(zip(symbols, row)), simultaneous=True))
                     for equation in equations]
        if any(residual.is_zero is False for residual in residuals):
            continue
        if any(residual.is_zero is not True for residual in residuals):
            raise RewriteError("cannot solve this system in closed form")
        if any(item.free_symbols - parameters for item in row):
            raise RewriteError("has infinitely many solutions")
        if any(item.has(sympy.nan, sympy.zoo, sympy.oo, -sympy.oo) for item in row):
            raise RewriteError("cannot solve this system in closed form")
        if domain == "real":
            reality = [sympy.simplify(item).is_real for item in row]
            if any(real is False for real in reality):
                continue
            if any(real is None for real in reality):
                raise RewriteError("cannot determine whether this system solution is real")
        accepted.append(row)
    return accepted


def _quoted_name(unknown: Any) -> sympy.Symbol:
    if not isinstance(unknown, ExpressionValue) or not isinstance(
            unknown.node, Var | BackslashRef):
        raise RewriteError("the unknown must be a quoted name, like `(x)")
    return sympy.Symbol(unknown.node.ch if isinstance(unknown.node, Var)
                        else unknown.node.name)


def _unknown(origin: Source, unknown: Any) -> sympy.Symbol:
    if unknown is not None:
        return _quoted_name(unknown)
    free = sorted(origin.expr.free_symbols, key=lambda s: s.name)
    if origin.params:
        if len(origin.params) != 1:
            raise RewriteError("needs the unknown when the function has several parameters")
        return origin.params[0]
    if len(free) != 1:
        if not free:
            raise RewriteError("has no unknown")
        names = ", ".join(s.name for s in free)
        raise RewriteError(f"needs the unknown when there are several free names: {names}")
    return free[0]

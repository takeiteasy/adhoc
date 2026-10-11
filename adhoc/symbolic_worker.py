"""Reusable spawn worker and syntax-only snapshots for symbolic requests."""

import atexit
import importlib
import multiprocessing
import pickle
import threading
import time
from dataclasses import dataclass, fields
from typing import Any

from .syntax import BackslashRef, Node, Var
from .tensor import ArrayValue


@dataclass
class FunctionBody:
    node: Node
    source: str


@dataclass
class FunctionSnapshot:
    name: str | None
    params: tuple[str, ...]
    body: FunctionBody
    closure: Any = None

    def __call__(self, *args):
        raise TypeError("symbolic function snapshots cannot be executed")


@dataclass
class Bindings:
    values: dict

    def _lookup(self, name):
        from .runtime import PRELUDE, _MISSING
        return self.values.get(name, PRELUDE.get(name, _MISSING))


@dataclass
class QuoteBindings:
    value: Any
    engine: Any

    def capture(self):
        from .expression import ExpressionValue
        from .units import UnitValue, Quantity
        captured = {}
        if self.engine is not None:
            inputs = self.value.items if isinstance(self.value, ArrayValue) else (self.value,)
            for item in inputs:
                if isinstance(item, ExpressionValue):
                    for name in _names(item.node):
                        bound = self.engine._lookup(name)
                        if isinstance(bound, UnitValue | Quantity):
                            captured[name] = bound
        return captured


@dataclass(frozen=True)
class CallableRef:
    module: str
    name: str


@dataclass(frozen=True)
class PreludeRef:
    name: str


def _names(value):
    if isinstance(value, Var):
        yield value.ch
    elif isinstance(value, BackslashRef):
        yield value.name
    elif isinstance(value, Node):
        for entry in fields(value):
            yield from _names(getattr(value, entry.name))
    elif isinstance(value, tuple):
        for item in value:
            yield from _names(item)


def snapshot(value, memo=None):
    from .runtime import AdFunction, PreludeFn, _MISSING
    memo = {} if memo is None else memo
    if isinstance(value, QuoteBindings):
        return snapshot(value.capture(), memo)
    if isinstance(value, AdFunction):
        if id(value) in memo:
            return memo[id(value)]
        result = FunctionSnapshot(value.name, value.params,
                                  FunctionBody(value.body.node, value.body.source))
        memo[id(value)] = result
        captured = {}
        for name in set(_names(value.body.node)) - set(value.params):
            bound = value if name == value.name else value.closure._lookup(name)
            if bound is _MISSING:
                continue
            if isinstance(bound, AdFunction) or not callable(bound):
                captured[name] = snapshot(bound, memo)
            elif isinstance(bound, PreludeFn):
                captured[name] = PreludeRef(bound.name)
            else:
                captured[name] = PreludeRef('')
        result.closure = Bindings(captured)
        return result
    if isinstance(value, PreludeFn):
        return PreludeRef(value.name)
    if isinstance(value, ArrayValue):
        return ArrayValue(tuple(snapshot(item, memo) for item in value.items))
    if isinstance(value, tuple):
        return tuple(snapshot(item, memo) for item in value)
    if isinstance(value, list):
        return [snapshot(item, memo) for item in value]
    if isinstance(value, dict):
        return {key: snapshot(item, memo) for key, item in value.items()}
    if callable(value):
        module, name = getattr(value, '__module__', None), getattr(value, '__qualname__', '')
        if not name:
            return PreludeRef('')
        if not module or '<' in name:
            from .rewrite import RewriteError
            raise RewriteError("needs an importable symbolic operation")
        return CallableRef(module, name)
    return value


def restore(value, memo=None):
    memo = {} if memo is None else memo
    if isinstance(value, CallableRef):
        result = importlib.import_module(value.module)
        for part in value.name.split('.'):
            result = getattr(result, part)
        return result
    if isinstance(value, PreludeRef):
        from .runtime import PRELUDE
        return PRELUDE.get(value.name, _opaque_callable)
    if isinstance(value, FunctionSnapshot):
        if id(value) in memo:
            return memo[id(value)]
        memo[id(value)] = value
        value.closure.values = restore(value.closure.values, memo)
        return value
    if isinstance(value, ArrayValue):
        return ArrayValue(tuple(restore(item, memo) for item in value.items))
    if isinstance(value, tuple):
        return tuple(restore(item, memo) for item in value)
    if isinstance(value, list):
        return [restore(item, memo) for item in value]
    if isinstance(value, dict):
        return {key: restore(item, memo) for key, item in value.items()}
    return value


def _opaque_callable(*args):
    raise TypeError("Python callables are not executed during rewriting")


def _serve(connection):
    from . import rewrite
    rewrite._IN_WORKER = True
    try:
        while True:
            request = connection.recv()
            try:
                operation, arguments = restore(request)
                payload = ('ok', operation(*arguments))
            except BaseException as error:
                payload = ('error', error)
            try:
                encoded = pickle.dumps(payload)
            except Exception:
                encoded = pickle.dumps(('error', rewrite.RewriteError(
                    "returned a result that cannot be sent back")))
            connection.send_bytes(encoded)
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class Worker:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.connection = None

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.kill()
            self.process.join()
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def run(self, operation, arguments, seconds):
        from .rewrite import RewriteError
        deadline = time.monotonic() + seconds
        timeout = RewriteError(f"took longer than {seconds:g}s")
        if not self.lock.acquire(timeout=max(0, deadline - time.monotonic())):
            raise timeout
        done = threading.Event()
        outcome = []
        transfer = None
        try:
            if self.process is None:
                context = multiprocessing.get_context('spawn')
                parent, child = context.Pipe()
                self.connection = parent
                self.process = context.Process(target=_serve, args=(child,), daemon=True)
                try:
                    self.process.start()
                except Exception as error:
                    self.process = None
                    parent.close()
                    self.connection = None
                    raise RewriteError(f"could not start symbolic worker: {error}") from None
                finally:
                    child.close()
            connection = self.connection

            def communicate():
                try:
                    request = snapshot((operation, arguments))
                    connection.send(request)
                    outcome.append(pickle.loads(connection.recv_bytes()))
                except Exception as error:
                    outcome.append(('transport', error))
                finally:
                    done.set()

            transfer = threading.Thread(target=communicate, daemon=True)
            transfer.start()
            if not done.wait(max(0, deadline - time.monotonic())):
                raise timeout
            status, payload = outcome[0]
            if status == 'transport':
                self.close()
                if isinstance(payload, RewriteError):
                    raise payload
                raise RewriteError(f"stopped unexpectedly: {payload}") from None
            if status == 'error':
                raise payload
            return payload
        except BaseException:
            if not done.is_set():
                self.close()
            raise
        finally:
            if transfer is not None:
                transfer.join(timeout=1)
            self.lock.release()


WORKER = Worker()
atexit.register(WORKER.close)

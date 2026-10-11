"""Importable operations and backend replacements for real spawn tests."""

import importlib
import os
import time


def identity(value=None):
    return value


def spin(*args, **kwargs):
    while True:
        pass


def swallow(*args, **kwargs):
    while True:
        try:
            spin()
        except Exception:
            pass


def boom():
    raise NotImplementedError('no')


def die():
    os._exit(1)


def unpicklable():
    return lambda: 1


def delay(seconds):
    time.sleep(seconds)
    return seconds


def slow_conversion(*args):
    time.sleep(1)


def side_operation(expression):
    from adhoc.symbolic_worker import WORKER
    if str(expression) == WORKER.test_side:
        spin()
    return expression


def patched_call(operation, arguments, patches):
    saved = []
    try:
        for module, path, replacement, constant in patches:
            owner = importlib.import_module(module)
            parts = path.split('.')
            for part in parts[:-1]:
                owner = getattr(owner, part)
            name = parts[-1]
            saved.append((owner, name, getattr(owner, name, None), hasattr(owner, name)))
            if constant:
                def returned(*args, _value=replacement, **kwargs):
                    return _value
                replacement = returned
            if operation is getattr(owner, name, None):
                operation = replacement
            setattr(owner, name, replacement)
        return operation(*arguments)
    finally:
        for owner, name, value, existed in reversed(saved):
            if existed:
                setattr(owner, name, value)
            else:
                delattr(owner, name)

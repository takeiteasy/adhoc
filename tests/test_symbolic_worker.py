import multiprocessing
import threading
import time

import pytest

from adhoc import rewrite
from adhoc.driver import run_source
from adhoc.symbolic_worker import WORKER
from worker_helpers import boom, delay, die, identity, spin, swallow, unpicklable


@pytest.fixture(autouse=True)
def reset_worker(monkeypatch):
    WORKER.close()
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '5')
    yield
    WORKER.close()


def test_spawn_and_reuse():
    assert rewrite.run_limited(identity, 17) == 17
    first = WORKER.process.pid
    assert WORKER.process._start_method == 'spawn'
    assert rewrite.run_limited(identity, 23) == 23
    assert WORKER.process.pid == first


@pytest.mark.parametrize('operation', [spin, swallow])
def test_timeout_kills_warm_worker_and_next_call_recovers(operation, monkeypatch):
    rewrite.run_limited(identity)
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '0.1')
    started = time.monotonic()
    with pytest.raises(rewrite.RewriteError, match='took longer than 0.1s'):
        rewrite.run_limited(operation)
    assert time.monotonic() - started < 2
    assert WORKER.process is None
    assert not multiprocessing.active_children()
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '5')
    assert rewrite.run_limited(identity, 'recovered') == 'recovered'


def test_cold_start_counts_against_deadline(monkeypatch):
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '0.001')
    with pytest.raises(rewrite.RewriteError, match='took longer'):
        rewrite.run_limited(identity)
    assert WORKER.process is None


def test_error_and_unpicklable_result_leave_worker_usable():
    with pytest.raises(NotImplementedError, match='no'):
        rewrite.run_limited(boom)
    pid = WORKER.process.pid
    with pytest.raises(rewrite.RewriteError, match='cannot be sent back'):
        rewrite.run_limited(unpicklable)
    assert rewrite.run_limited(identity, 1) == 1
    assert WORKER.process.pid == pid


def test_crash_is_reaped_and_replaced():
    with pytest.raises(rewrite.RewriteError, match='stopped unexpectedly'):
        rewrite.run_limited(die)
    assert not multiprocessing.active_children()
    assert rewrite.run_limited(identity, 'next') == 'next'


def test_queued_timeout_does_not_kill_active_job(monkeypatch):
    rewrite.run_limited(identity)
    pid = WORKER.process.pid
    result = []
    thread = threading.Thread(target=lambda: result.append(rewrite.run_limited(delay, 0.4)))
    thread.start()
    deadline = time.monotonic() + 2
    while not WORKER.lock.locked() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert WORKER.lock.locked()
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '0.05')
    with pytest.raises(rewrite.RewriteError, match='took longer'):
        rewrite.run_limited(identity)
    thread.join(timeout=3)
    assert result == [0.4]
    assert WORKER.process.pid == pid


def test_large_messages_round_trip_without_blocking_forever():
    value = 'x' * (2 * 1024 * 1024)
    assert rewrite.run_limited(identity, value) == value


def test_library_function_snapshot_ignores_unrelated_unpicklable_bindings():
    env = {'unused': lambda: None}
    result = run_source('a=3\ng(t)=a t^2\nf(x)=g(x)+1\n\\deriv(f)', env)
    assert result[-1] == r'= \expr((6 * x))'
    assert env['unused'] is not None


def test_local_operations_fail_promptly_but_unlimited_mode_stays_inline(monkeypatch):
    with pytest.raises(rewrite.RewriteError, match='importable'):
        rewrite.run_limited(lambda: 1)
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', '0')
    assert rewrite.run_limited(lambda: 1) == 1


@pytest.mark.parametrize('seconds', ['nan', 'inf'])
def test_nonfinite_timeout_is_an_error(monkeypatch, seconds):
    monkeypatch.setenv('ADHOC_SYMBOLIC_TIMEOUT', seconds)
    with pytest.raises(rewrite.RewriteError, match='finite'):
        rewrite.run_limited(identity)


def test_startup_failure_does_not_execute_inline(monkeypatch):
    context = multiprocessing.get_context('spawn')
    monkeypatch.setattr(type(context.Process()), 'start', lambda self: (_ for _ in ()).throw(OSError('unavailable')))
    with pytest.raises(rewrite.RewriteError, match='could not start symbolic worker'):
        rewrite.run_limited(identity)
    assert WORKER.process is None


def test_captured_callable_shadowing_a_constant_stays_symbolic():
    result = run_source('i=\\py("math.sin")\nf(x)=i(x)\n\\simplify(f)', {})
    assert result[-1] == r'= \expr(i(x))'

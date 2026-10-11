import pytest

from adhoc import rewrite
from adhoc.symbolic_worker import WORKER
from worker_helpers import identity, patched_call


@pytest.fixture
def worker_patch(monkeypatch):
    original = rewrite.run_limited
    patches = []

    def limited(operation, *arguments):
        with monkeypatch.context() as warmup:
            warmup.setenv('ADHOC_SYMBOLIC_TIMEOUT', '5')
            original(identity)
        return original(patched_call, operation, arguments, patches)

    def patch(module, path, replacement, *, constant=False):
        patches.append((module, path, replacement, constant))
        monkeypatch.setattr(rewrite, 'run_limited', limited)

    yield patch
    WORKER.close()

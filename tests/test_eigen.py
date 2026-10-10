import multiprocessing
import time

import numpy as np
import pytest
import sympy

from adhoc import eigen, linalg, runtime
from adhoc.driver import run_source
from adhoc.runtime import Algebraic, EvalError, NumError, PRELUDE, RRA, neq, nmul
from adhoc.tensor import TensorValue, contract


def matrix(rows):
    return TensorValue((len(rows), len(rows[0])), tuple(v for row in rows for v in row))


def eig(rows):
    return PRELUDE["eig"](matrix(rows))


def check_exact(rows):
    a = matrix(rows)
    records = PRELUDE["eig"](a).items
    assert sum(record.items[1] for record in records) == a.shape[0]
    for record in records:
        value, multiplicity, basis = record.items
        assert 1 <= basis.shape[1] <= multiplicity
        for c in range(basis.shape[1]):
            vector = TensorValue((a.shape[0],), basis.items[c::basis.shape[1]])
            assert neq(contract(runtime.nmul, runtime.nadd, a, vector),
                       TensorValue(vector.shape, tuple(nmul(value, v) for v in vector.items)))
            assert next(v for v in vector.items if not neq(v, 0)) == 1
    return records


@pytest.mark.parametrize("rows", [
    [[5]], [[0, 0], [0, 0]], [[1, 0], [0, 1]], [[1, 0], [0, 2]],
    [[0, -1], [1, 0]], [[0, 2], [1, 0]],
])
def test_exact_eigenpairs(rows):
    check_exact(rows)


def test_repeated_and_defective_eigenspaces():
    identity = check_exact([[1, 0], [0, 1]])
    assert len(identity) == 1
    assert identity[0].items[1:] == (2, matrix([[1, 0], [0, 1]]))
    defective = check_exact([[1, 1], [0, 1]])
    assert len(defective) == 1
    assert defective[0].items == (1, 2, matrix([[1], [0]]))


def test_exact_numeric_tiers():
    from fractions import Fraction
    from adhoc.gauss import Gaussian
    from adhoc.symbolic import PI

    check_exact([[Fraction(1, 2), 1], [0, Fraction(3, 2)]])
    check_exact([[Gaussian(Fraction(0), Fraction(1)), 1], [0, 2]])
    root = runtime.npow(2, Fraction(1, 3))
    check_exact([[root, 1], [0, 2]])
    records = check_exact([[PI, 1], [1, 0]])
    assert all(isinstance(record.items[0], RRA) for record in records)


def test_language_indexing_and_display():
    assert run_source(r"\eig([1, 1; 0, 1])", {})[-1] == "= ⟨⟨1, 2, [1; 0]⟩⟩"
    env = {}
    run_source(r"x = \eig([1, 1; 0, 1])", env)
    assert run_source("x[1][2]", env)[-1] == "= 2"
    assert run_source("x[1][3][..,1]", env)[-1] == "= [1, 0]"
    assert run_source("a = [1, 1; 0, 1]; v = x[1][3][..,1]; w = a @ v; w = x[1][1] v", env)[-1] == "true"
    assert run_source(r"\map(\eig, ⟨[2;], [3;]⟩)", {})[-1] == \
        "= ⟨⟨⟨2, 1, [1;]⟩⟩, ⟨⟨3, 1, [1;]⟩⟩⟩"


def test_quintic_roots_without_radicals(monkeypatch):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "30")
    rows = [[0, 0, 0, 0, 1], [1, 0, 0, 0, 1], [0, 1, 0, 0, 0],
            [0, 0, 1, 0, 0], [0, 0, 0, 1, 0]]
    records = eig(rows).items
    assert len(records) == 5
    for record in records:
        value, multiplicity, basis = record.items
        assert isinstance(value, Algebraic)
        assert value.expr.has(sympy.CRootOf)
        assert multiplicity == 1 and basis.shape == (5, 1)
        assert not any(isinstance(v, float | complex) for v in basis.items)
        root = complex(value.expr.evalf(20))
        assert abs(root**5 - root - 1) < 1e-12
        vector = np.array([complex(runtime.value_to_sympy(v).evalf(20)) for v in basis.items])
        assert np.linalg.norm(np.array(rows) @ vector - root * vector) < 1e-10


def test_eigen_demo():
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "demos" / "eigen.ad"
    outputs = run_source(source.read_text(), {})
    assert "true" in outputs
    assert len(outputs) == 11


@pytest.mark.parametrize("rows", [
    [[5.]], [[0., 0], [0, 0]], [[1., 0], [0, 1]], [[1., 1], [0, 1]],
    [[0., -1], [1, 0]], [[1., 1j], [-1j, 2]], [[1., 0], [0, 1. + 1e-9]],
    [[1e100, 2e100], [0., 3e100]],
])
def test_numerical_residuals_and_scaling(rows):
    a = np.asarray(rows, dtype=complex)
    records = eig(rows).items
    assert len(records) == len(rows)
    for record in records:
        value, multiplicity, basis = record.items
        assert isinstance(value, float | complex)
        assert multiplicity == 1 and basis.shape == (len(rows), 1)
        assert all(isinstance(v, float | complex) for v in basis.items)
        vector = np.asarray(basis.items, dtype=complex)
        scale = max(1., np.linalg.norm(a) + abs(value))
        assert np.linalg.norm(a @ vector - value * vector) / scale < 1e-12
        assert np.linalg.norm(vector) == pytest.approx(1.)
        pivot = vector[np.argmax(abs(vector))]
        assert pivot.real > 0 and pivot.imag == 0


def test_float_selects_whole_matrix_backend():
    from adhoc.symbolic import PI

    result = eig([[PI, 0], [0, 1.]]).items
    assert all(isinstance(record.items[0], float) for record in result)
    close = eig([[1., 0], [0, 1. + 1e-9]]).items
    assert close[0].items[0] != close[1].items[0]


@pytest.mark.parametrize("source, message", [
    (r"\eig()", "1 argument"), (r"\eig([1;], [2;])", "1 argument"),
    (r"\eig(2)", "needs a matrix"), (r"\eig([1, 2])", "needs a matrix"),
    (r"\eig([1, 2, 3; 4, 5, 6])", "square matrix"),
    (r'\eig(["a";])', "strings are not numbers"),
    (r"\eig([\true;])", "booleans are not numbers"),
    (r"\eig([\inf;])", "finite numeric entries"),
    (r"\eig([\nan;])", "finite numeric entries"),
    (r"\eig = 1", "protected|cannot"),
])
def test_language_errors(source, message):
    with pytest.raises(EvalError, match=message):
        run_source(source, {})


def test_errors_retain_call_span():
    source = r"1 + \eig([1, 2])"
    with pytest.raises(EvalError) as caught:
        run_source(source, {})
    span = caught.value.span
    assert source[span.start:span.end] == r"\eig([1, 2])"


def test_numerical_conversion_overflow():
    with pytest.raises(NumError, match="finite floats"):
        eig([[10**1000, 0], [0, 1.]])


def test_numerical_nonconvergence(monkeypatch):
    def fail(_):
        raise np.linalg.LinAlgError("failed")

    monkeypatch.setattr(np.linalg, "eig", fail)
    with pytest.raises(NumError, match="did not converge"):
        eig([[1.]])


def test_numerical_nonfinite_result(monkeypatch):
    monkeypatch.setattr(np.linalg, "eig", lambda _: (np.array([np.inf]), np.array([[1.]])))
    with pytest.raises(NumError, match="result is not finite"):
        eig([[1.]])


def test_exact_unsupported_is_not_approximated(monkeypatch):
    def fail(*args, **kwargs):
        raise NotImplementedError

    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0")
    monkeypatch.setattr(sympy.Matrix, "eigenvects", fail)
    with pytest.raises(NumError, match="cannot compute this exact"):
        eig([[1]])


def test_exact_unrepresentable_result_is_not_approximated(monkeypatch):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0")
    monkeypatch.setattr(eigen, "exact", lambda _: [(sympy.Symbol("x"), 1, [[sympy.Integer(1)]])])
    with pytest.raises(NumError, match="cannot convert"):
        eig([[1]])


def test_constructed_size_limit(monkeypatch):
    monkeypatch.setattr(linalg, "MAX_ITEMS", 3)
    with pytest.raises(NumError, match="over the limit"):
        eig([[1, 0], [0, 1]])


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="requires fork")
def test_timeout_includes_result_conversion(monkeypatch):
    monkeypatch.setenv("ADHOC_SYMBOLIC_TIMEOUT", "0.05")
    monkeypatch.setattr(runtime, "_sympy_to_ad", lambda *args: time.sleep(1))
    with pytest.raises(NumError, match="took longer"):
        eig([[1]])
    assert not multiprocessing.active_children()

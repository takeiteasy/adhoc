import sys
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from adhoc.driver import run_source
from adhoc.gauss import Gaussian
from adhoc.runtime import EvalError, NumError, PRELUDE, npow
from adhoc.tensor import TensorValue


def ev(src, env=None):
    return run_source(src, {} if env is None else env)[-1]


def fails(src, message, env=None):
    with pytest.raises(EvalError, match=message):
        run_source(src, {} if env is None else env)


def test_det_and_trace_are_exact():
    assert ev("\\det([1, 2; 3, 4])") == "= -2"
    assert ev("\\det([1/2, 1; 1, 3])") == "= 1/2"
    assert ev("\\det([√2, 1; 1, √2])") == "= 1"
    assert ev("\\det([1, 2; 2, 4])") == "= 0"
    assert ev("\\det([5;])") == "= 5"
    assert ev("\\tr([1, 2; 3, 4])") == "= 5"


def test_det_tracks_row_swaps():
    assert ev("\\det([0, 1; 1, 0])") == "= -1"
    assert ev("\\det([0, 2, 0; 1, 0, 0; 0, 0, 3])") == "= -6"


def test_inverse_is_exact():
    assert ev("\\inv([1, 2; 3, 4])") == "= [-2, 1; 3/2, -1/2]"
    env = {}
    run_source("m = [2, 1, 0; 1, 3, 1; 0, 1, 4]", env)
    assert ev("\\inv(m) @ m", env) == "= [1, 0, 0; 0, 1, 0; 0, 0, 1]"
    assert ev("\\inv([2., 1; 1, 3])", env) == "= [0.6, -0.2; -0.2, 0.4]"


def test_float_elimination_pivots_by_size():
    assert ev("\\inv([1e-20, 1; 1, 1]) @ [1e-20, 1; 1, 1]") == "= [1.0, 0.0; 0.0, 1.0]"


def test_singular_and_shape_errors():
    fails("\\inv([1, 2; 2, 4])", "singular")
    fails("\\linsolve([1, 2; 2, 4], [1, 2])", "singular")
    fails("\\det([1, 2, 3; 4, 5, 6])", "square matrix, got shape 2x3")
    fails("\\det([1, 2, 3])", "needs a matrix")
    fails("\\det(3)", "needs a matrix")
    fails("\\tr([1, 2, 3])", "needs a matrix")


def test_linsolve_vector_and_matrix_right_hand_sides():
    assert ev("\\linsolve([2, 1; 1, 3], [3, 5])") == "= [4/5, 7/5]"
    assert ev("\\linsolve([2, 0; 0, 4], [2, 0; 0, 4])") == "= [1, 0; 0, 1]"
    fails("\\linsolve([2, 1; 1, 3], [1, 2, 3])", "right-hand side with 2 rows")


def test_rank_and_rref():
    assert ev("\\rank([1, 2; 2, 4])") == "= 1"
    assert ev("\\rank([1, 0; 0, 1])") == "= 2"
    assert ev("\\rank([1, 2, 3; 4, 5, 6; 7, 8, 9])") == "= 2"
    assert ev("\\rref([1, 2, 3; 4, 5, 6])") == "= [1, 0, -1; 0, 1, 2]"
    assert ev("\\rref([0, 0; 0, 0])") == "= [0, 0; 0, 0]"


def test_constructors():
    assert ev("\\eye(2)") == "= [1, 0; 0, 1]"
    assert ev("\\zeros(2, 3)") == "= [0, 0, 0; 0, 0, 0]"
    assert ev("\\zeros(2)") == "= [0, 0]"
    assert ev("\\ones(2, 2)") == "= [1, 1; 1, 1]"
    assert ev("\\diag([1, 2])") == "= [1, 0; 0, 2]"
    assert ev("\\diag([1, 2; 3, 4])") == "= [1, 4]"
    assert ev("\\diag([1, 2, 3; 4, 5, 6])") == "= [1, 5]"
    fails("\\eye(0)", "positive size")
    fails("\\zeros(0)", "positive integers")
    fails("\\zeros()", "positive integers")
    fails("\\zeros(1/2)", "exact integer")
    fails("\\zeros(2000, 2000)", "over the limit")
    fails("\\diag(3)", "needs a matrix")


def test_cross_and_times():
    assert ev("[1, 0, 0] × [0, 1, 0]") == "= [0, 0, 1]"
    assert ev("[1, 2, 3] \\times [4, 5, 6]") == "= [-3, 6, -3]"
    assert ev("\\cross([1, 2, 3], [4, 5, 6])") == "= [-3, 6, -3]"
    assert ev("2 × 3") == "= 6"
    assert ev("2 × [1, 2]") == "= [2, 4]"
    fails("[1, 2] × [3, 4]", "length 3")
    fails("\\cross(1, [1, 2, 3])", "length 3")


def test_outer_and_kronecker():
    assert ev("[1, 2] ⊗ [3, 4]") == "= [3, 4; 6, 8]"
    assert ev("[1, 2] \\otimes [3, 4]") == "= [3, 4; 6, 8]"
    assert ev("\\outer([1, 2], [3, 4])") == "= [3, 4; 6, 8]"
    assert ev("3 ⊗ [1, 2]") == "= [3, 6]"
    assert ev("\\shape([1, 2] ⊗ [1, 2; 3, 4])") == "= [2, 2, 2]"
    assert ev("\\kron([1, 2], [3, 4])") == "= [3, 4, 6, 8]"
    assert ev("\\kron([1, 2; 3, 4], [1, 1; 1, 1])") == \
        "= [1, 1, 2, 2; 1, 1, 2, 2; 3, 3, 4, 4; 3, 3, 4, 4]"
    fails("\\kron([1, 2], [1, 2; 3, 4])", "two vectors or two matrices")
    fails("\\outer(1, 2)", "two tensors")


def test_times_operators_are_values_and_sections():
    assert ev("(×)([1, 0, 0], [0, 1, 0])") == "= [0, 0, 1]"
    assert ev("([1, 0, 0] ×)([0, 0, 1])") == "= [0, -1, 0]"
    assert ev("(⊗)([1, 2], [3, 4])") == "= [3, 4; 6, 8]"
    assert ev("\\map((2 ×), [1, 2])") == "= [2, 4]"


def test_times_binds_with_the_multiplicative_level():
    assert ev("1 + 2 × 3") == "= 7"
    assert ev("2 × 3 ^ 2") == "= 18"


def test_norm():
    assert ev("\\norm([3, 4])") == "= 5"
    assert ev("\\norm(-3)") == "= 3"
    assert ev("\\norm([3, 4; 0, 0])") == "= 5"
    env = {}
    run_source("n = \\norm([1, i])", env)
    assert ev("n = √2", env) == "true"
    run_source("m = \\norm([1, 1])", env)
    assert ev("m = √2", env) == "true"
    assert ev("\\norm([3., 4.])") == "= 5.0"


def test_reshape_concat_stack():
    assert ev("\\reshape([1, 2, 3, 4], 2, 2)") == "= [1, 2; 3, 4]"
    assert ev("\\reshape([1, 2; 3, 4], 4)") == "= [1, 2, 3, 4]"
    fails("\\reshape([1, 2, 3], 2, 2)", "3 into 2x2")
    fails("\\reshape(1, 1)", "needs a tensor")
    assert ev("\\concat([1, 2], [3])") == "= [1, 2, 3]"
    assert ev("\\concat([1, 2; 3, 4], [5, 6;])") == "= [1, 2; 3, 4; 5, 6]"
    assert ev("\\concat(⟨1⟩, ⟨2, 3⟩)") == "= ⟨1, 2, 3⟩"
    fails("\\concat([1, 2; 3, 4], [1, 2, 3])", "same shape")
    fails("\\concat([1], ⟨2⟩)", "tensors, or arrays")
    fails("\\concat([1])", "two or more")
    assert ev("\\stack([1, 2], [3, 4])") == "= [1, 2; 3, 4]"
    assert ev("\\stack(1, 2, 3)") == "= [1, 2, 3]"
    fails("\\stack([1, 2], [3])", "different shapes")
    fails('\\stack("a")', "strings are not numbers")


def test_names_are_protected():
    fails("\\det = 1", "protected|cannot")


def matrix(rows):
    return TensorValue((len(rows), len(rows[0])), tuple(v for row in rows for v in row))


@pytest.mark.parametrize("multiplier", [1, 1j])
def test_near_singular_functions_agree(multiplier):
    a = matrix([[multiplier, multiplier],
                [multiplier, multiplier * (1 + sys.float_info.epsilon)]])
    env = {"m": a}
    assert ev(r"\rank(m)", env) == "= 1"
    for source in (r"\det(m)", r"\abs(m)", "|m|"):
        assert ev(source, env) == "= 0"
    assert PRELUDE["rref"](a).items == (1, 1, 0, 0)
    fails(r"\inv(m)", "singular", env)
    fails(r"\linsolve(m, [1, 1])", "singular", env)


def test_roundoff_does_not_count_as_rank():
    a = matrix([[1., 2., 3.], [4., 5., 6.], [7., 8., 9.]])
    assert PRELUDE["rank"](a) == 2
    assert PRELUDE["det"](a) == 0
    assert PRELUDE["rref"](a).items == pytest.approx((1, 0, -1, 0, 1, 2, 0, 0, 0))


@pytest.mark.parametrize("multiple, rank", [(1, 1), (2, 1), (4, 2)])
def test_machine_precision_cutoff(multiple, rank):
    a = matrix([[1., 0], [0, multiple * sys.float_info.epsilon]])
    assert PRELUDE["rank"](a) == rank
    assert PRELUDE["rref"](a).items == (1, 0, 0, rank - 1)
    if rank == 1:
        with pytest.raises(NumError, match="singular"):
            PRELUDE["inv"](a)
    else:
        assert PRELUDE["det"](a) > 0


@pytest.mark.parametrize("scale", [1e-300, 1e-100, 1., 1e100, 1e300])
def test_float_rank_and_inverse_are_scale_invariant(scale):
    a = matrix([[scale, 0], [0, scale]])
    assert PRELUDE["rank"](a) == 2
    assert PRELUDE["rref"](a).items == (1, 0, 0, 1)
    assert PRELUDE["inv"](a).items == pytest.approx((1 / scale, 0, 0, 1 / scale))
    singular = matrix([[scale, scale], [scale, scale * (1 + sys.float_info.epsilon)]])
    assert PRELUDE["rank"](singular) == 1
    assert PRELUDE["det"](singular) == 0


@pytest.mark.parametrize("rows, rank, reduced", [
    ([[0., 0., 0.], [0., 0., 0.]], 0, (0, 0, 0, 0, 0, 0)),
    ([[0., 1., 2.], [0., 2., 4.]], 1, (0, 1, 2, 0, 0, 0)),
    ([[0., 1.], [1., 0.], [0., 0.]], 2, (1, 0, 0, 1, 0, 0)),
])
def test_rectangular_float_rref(rows, rank, reduced):
    a = matrix(rows)
    assert PRELUDE["rank"](a) == rank
    assert PRELUDE["rref"](a).items == reduced


def test_pivot_cutoff_precedes_normalization():
    a = matrix([[1e-10, 1.], [1e-10, 1 + sys.float_info.epsilon]])
    assert PRELUDE["rank"](a) == 1
    assert PRELUDE["rref"](a).items == (1, 1e10, 0, 0)
    assert PRELUDE["rref"](matrix([[1e20, 1e10, 1.], [0, 1e20, 1.]])).items == \
        pytest.approx((1, 0, 1e-20 - 1e-30, 0, 1, 1e-20), rel=1e-12, abs=0)


def test_small_factors_and_rhs_are_not_trimmed():
    a = matrix([[1., 1.], [1e-20, 1.]])
    assert PRELUDE["inv"](a).items[2] == -1e-20
    right = TensorValue((2,), (1e-30, 1e-30))
    solution = PRELUDE["linsolve"](matrix([[1e20, 0], [0, 1e20]]), right)
    assert solution.items == pytest.approx((1e-50, 1e-50), rel=1e-12, abs=0)


@pytest.mark.parametrize("right", [
    TensorValue((2,), (1e100, 1e100)),
    matrix([[1e100, 0., 1e100], [0., 1e100, 1e100]]),
])
def test_rhs_does_not_select_or_scale_tolerance(right):
    tiny = Fraction(1, 10**20)
    for leading in (1, 1.):
        a = matrix([[leading, 0], [0, tiny]])
        if isinstance(leading, float):
            with pytest.raises(NumError, match="singular"):
                PRELUDE["linsolve"](a, right)
        else:
            result = PRELUDE["linsolve"](a, right)
            assert result.items[-1] == pytest.approx(1e120)
    a = matrix([[1e-20, 0], [0, 1e-20]])
    assert PRELUDE["linsolve"](a, right).items[-1] == pytest.approx(1e120)


@pytest.mark.parametrize("complex_values", [False, True])
def test_float_inverse_and_solve_residuals(complex_values):
    rows = [[0., 2., 1.], [3., 1., -1.], [1., 0., 4.]]
    if complex_values:
        rows[1][1] += 2j
    a = matrix(rows)
    numeric = np.array(rows)
    inverse = np.array(PRELUDE["inv"](a).items).reshape(3, 3)
    np.testing.assert_allclose(numeric @ inverse, np.eye(3), rtol=1e-12, atol=1e-12)
    assert PRELUDE["det"](a) == pytest.approx(np.linalg.det(numeric))
    for rhs in (TensorValue((3,), (1., 2., 3.)), matrix([[1., 2.], [3., 4.], [5., 6.]])):
        solution = PRELUDE["linsolve"](a, rhs)
        np.testing.assert_allclose(numeric @ np.array(solution.items).reshape(solution.shape),
                                   np.array(rhs.items).reshape(rhs.shape), rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("value", [
    Fraction(1, 10**30), Gaussian(Fraction(0), Fraction(1)),
    npow(2, Fraction(1, 2)), npow(2, Fraction(1, 3)),
])
def test_exact_numeric_tiers_keep_exact_pivots(value):
    a = matrix([[value, 0], [0, 1]])
    assert PRELUDE["rank"](a) == 2
    assert PRELUDE["det"](a) == value
    assert PRELUDE["rref"](a).items == (1, 0, 0, 1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), complex(1, float("inf"))])
@pytest.mark.parametrize("name", ["det", "inv", "rank", "rref", "linsolve"])
def test_nonfinite_elimination_inputs_have_spans(value, name):
    source = f"\\{name}(m" + (", [1, 2])" if name == "linsolve" else ")")
    with pytest.raises(EvalError, match="finite numeric entries") as error:
        run_source(source, {"m": matrix([[value, 0], [0, 1]])})
    assert error.value.span is not None
    assert source[error.value.span.start:error.value.span.end] == source


def test_nonfinite_rhs_is_rejected():
    fails(r"\linsolve([1, 0; 0, 1], [\inf, 1])", "finite numeric entries")


def test_tensor_demo():
    source = Path(__file__).resolve().parents[1] / "demos" / "tensors.ad"
    outputs = run_source(source.read_text(), {})
    assert outputs[-3:] == ["= 2", "= [1, 0.0, -1.0; 0.0, 1, 2.0; 0.0, 0, 0]", "= 0"]

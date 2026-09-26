import pytest

from adhoc.driver import run_source
from adhoc.runtime import EvalError


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

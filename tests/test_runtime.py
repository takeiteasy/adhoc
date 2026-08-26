import math

import pytest
from fractions import Fraction

from adhoc.runtime import (
    AdValue,
    DIVISION_BY_ZERO,
    NumError,
    ndiv,
    neq,
    nneg,
    npow,
    nshow,
    nadd,
    nmul,
    nsub,
    parse_literal,
)


def rat(n: int, d: int) -> Fraction:
    return Fraction(n, d)


# --- ports of num.rs's test suite ---


def test_exact_rational_sum_collapses_to_integer():
    a = rat(1, 3)
    total = nadd(nadd(a, a), a)
    assert nshow(total) == "1"
    assert isinstance(total, int)


def test_integer_division_collapses():
    r = ndiv(6, 2)
    assert nshow(r) == "3"
    assert isinstance(r, int)


def test_npow_negative_integer_exponent_is_exact():
    assert nshow(npow(2, -1)) == "1/2"


def test_division_by_zero_is_typed():
    with pytest.raises(NumError) as e:
        ndiv(1, 0)
    assert e.value.args[0] == DIVISION_BY_ZERO


def test_zero_to_negative_power_is_typed_division_by_zero():
    with pytest.raises(NumError) as e:
        npow(0, -1)
    assert e.value.args[0] == DIVISION_BY_ZERO


def test_neq_compares_exact_values():
    assert neq(rat(1, 2), rat(2, 4)) is True
    assert neq(1, 2) is False


def test_display_matches_pinned_forms():
    assert nshow(rat(1, 2)) == "1/2"
    assert nshow(rat(1, 3)) == "1/3"
    assert nshow(2) == "2"
    assert nshow(7) == "7"


def test_float_display_parity():
    assert nshow(nadd(0.5, 0.5)) == "1.0"
    assert nshow(1.0) == "1.0"
    assert nshow(math.sqrt(2.0)) == "1.4142135623730951"


# --- ports of tests/grammar.rs's float parity pins ---


def test_grammar_float_parity():
    assert nshow(nadd(0.5, 0.5)) == "1.0"
    assert nshow(npow(2, 0.5)) == "1.4142135623730951"


# --- tier promotion ---


def test_int_and_rational_promote_to_rational():
    assert nshow(nadd(1, rat(1, 2))) == "3/2"
    assert isinstance(nadd(1, rat(1, 2)), Fraction)


def test_rational_and_float_promote_to_float():
    out = nadd(rat(1, 2), 0.25)
    assert isinstance(out, float)
    assert nshow(out) == "0.75"


def test_sub_and_mul_across_tiers():
    assert nsub(1, rat(1, 3)) == rat(2, 3)
    assert nmul(rat(2, 3), 3) == 2
    assert nsub(2.5, 1) == 1.5


def test_exact_base_stays_exact_for_integer_exponent():
    assert nshow(npow(rat(3, 2), 2)) == "9/4"


def test_negative_odd_exponent_on_negative_base():
    # (-2)^-3 = -1/8
    assert nshow(npow(-2, -3)) == "-1/8"


def test_fraction_valued_exponent_collapses_to_integer_path():
    # A denominator-1 rational exponent behaves as an integer exponent (as_integer_exponent).
    assert nshow(npow(2, Fraction(3))) == "8"


def test_neg_preserves_type():
    assert nneg(3) == -3
    assert nneg(rat(1, 2)) == rat(-1, 2)
    assert nneg(1.5) == -1.5


# --- pinned MPFR-semantics divergences (module docstring / docs/numerics.md) ---


def test_float_division_by_zero_yields_signed_inf_or_nan():
    assert nshow(ndiv(1.0, 0.0)) == "Inf"
    assert nshow(ndiv(-1.0, 0.0)) == "-Inf"
    assert nshow(ndiv(1.5, 0.0)) == "Inf"
    assert nshow(ndiv(0.0, 0.0)) == "NaN"


def test_float_pow_overflow_saturates_to_inf():
    assert nshow(npow(10.0, 400.0)) == "Inf"
    assert nshow(npow(-10.0, 401.0)) == "-Inf"


def test_negative_base_fractional_pow_is_nan_not_complex():
    v = npow(-8.0, 0.5)
    assert isinstance(v, float)
    assert math.isnan(v)
    assert nshow(v) == "NaN"


def test_zero_base_negative_float_power_is_inf():
    assert nshow(npow(0.0, -1.5)) == "Inf"


# --- display policy: no scientific notation ---


def test_large_magnitude_display_expands_positionally():
    assert nshow(1e16) == "10000000000000000.0"
    big = float(10**30)
    assert nshow(big) == f"{10**30}.0"


def test_small_magnitude_display_expands_positionally():
    assert nshow(1e-7) == "0.0000001"


# --- literal parsing ---


def test_parse_literal_tiers_by_dot():
    assert parse_literal("42") == 42
    assert isinstance(parse_literal("42"), int)
    assert parse_literal("0.5") == 0.5
    assert isinstance(parse_literal("0.5"), float)


def test_values_are_plain_python_types():
    # The whole point of the seam mapping: adhoc values ARE int/Fraction/float, which is
    # what lets Python libraries consume them directly.
    v: AdValue = ndiv(1, 4)
    assert isinstance(v, Fraction)
    assert float(v) * 8 == 2.0

import math
import numbers

import pytest
from fractions import Fraction

from adhoc.runtime import (
    AdValue,
    EvalError,
    DIVISION_BY_ZERO,
    NOT_A_NUMBER,
    STRINGS_NOT_NUMBERS,
    NumError,
    _to_ad,
    ndiv,
    neq,
    nneg,
    npow,
    nshow,
    nadd,
    nmul,
    nsub,
    parse_literal,
    RangeValue,
    _agree,
    _as_float,
    _settled,
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


def test_range_value_is_lazy_and_inclusive():
    values = iter(RangeValue(1, 1, 3))
    assert [next(values) for _ in range(3)] == [1, 2, 3]
    assert nshow(RangeValue(1, 1, 3)) == "<range 1..3>"


def test_range_value_supports_descending_and_inferred_steps():
    assert list(RangeValue(10, -2, 1, 8)) == [10, 8, 6, 4, 2]
    assert list(RangeValue(1, Fraction(1, 2), 2)) == [1, Fraction(3, 2), 2]
    assert list(RangeValue(1, 2, 6)) == [1, 3, 5]


def test_range_zero_step_is_rejected_by_engine():
    from adhoc.driver import run_source

    with pytest.raises(EvalError, match="range step cannot be zero"):
        run_source("3,3..10")


def test_non_finite_range_bounds_are_rejected():
    # A non-finite bound would iterate forever (or never start) in the finite
    # loop; `a..` is the language's infinite form (docs/numerics.md).
    from adhoc.driver import run_source

    with pytest.raises(EvalError, match="range end must be a finite"):
        run_source("1..\\inf")
    with pytest.raises(EvalError, match="range end must be a finite"):
        run_source("1..\\nan")
    with pytest.raises(EvalError, match="range start must be a finite"):
        run_source("\\inf..3")
    with pytest.raises(EvalError, match="range step must be a finite"):
        run_source("1,\\inf..5")


def test_values_are_plain_python_types():
    # The whole point of the seam mapping: adhoc values ARE int/Fraction/float, which is
    # what lets Python libraries consume them directly.
    v: AdValue = ndiv(1, 4)
    assert isinstance(v, Fraction)
    assert float(v) * 8 == 2.0


# --- strings and callables at the seam (stage 5) ---


def test_string_display_round_trips():
    assert nshow('a"b\\c') == '"a\\"b\\\\c"'


def test_nadd_concatenates_two_strings():
    assert nadd("foo", "bar") == "foobar"
    assert nadd("", "x") == "x"


def test_seam_rejects_strings_as_typed_errors():
    for op in (nsub, nmul, ndiv, npow):
        with pytest.raises(NumError) as e:
            op("s", 1)
        assert e.value.args[0] == STRINGS_NOT_NUMBERS
        with pytest.raises(NumError):
            op(1, "s")
    with pytest.raises(NumError):
        nneg("s")
    # `+` concatenates only string×string: either side numeric is a typed error.
    with pytest.raises(NumError) as e:
        nadd("s", 1)
    assert e.value.args[0] == STRINGS_NOT_NUMBERS
    with pytest.raises(NumError):
        nadd(1, "s")


def test_seam_rejects_callables_with_number_message():
    for op in (nadd, nsub, nmul, ndiv, npow):
        with pytest.raises(NumError) as e:
            op(len, 1)
        assert e.value.args[0] == NOT_A_NUMBER


def test_neq_value_equality_for_strings_and_identity_fallback_for_others():
    assert neq("ab", "ab") is True
    assert neq("ab", "cd") is False
    assert neq("ab", 1) is False
    f = lambda: 0
    assert neq(f, f) is True
    assert neq(f, lambda: 0) is False
    assert neq(f, 1) is False


def test_callable_display_uses_module_qualname():
    assert nshow(math.sqrt) == "<py math.sqrt>"
    assert nshow(int) == "<py builtins.int>"


def test_matrix_rational_subclass_normalizes():
    class Half:
        numerator = 2
        denominator = 4

    numbers.Rational.register(Half)
    assert _to_ad(Half()) == rat(1, 2)


def test_matrix_bool_precedes_int():
    assert _to_ad(True) == 1 and isinstance(_to_ad(True), int)


# --- shared convergence mechanism (infinite folds + \lim) ---


def test_settled_exact_tiers_use_the_exact_tolerance():
    assert _settled(1, 1)
    assert not _settled(1, 2)
    near = Fraction(1, 3) + Fraction(1, 10**13)
    assert _settled(Fraction(1, 3), near)
    far = Fraction(1, 3) + Fraction(1, 10**11)
    assert not _settled(Fraction(1, 3), far)


def test_settled_float_tier_rejects_non_finite_deltas():
    assert _settled(0.5, 0.5)
    assert not _settled(float("nan"), 0.5)
    assert not _settled(float("inf"), float("inf"))


def test_agree_allows_two_plateau_radii_but_not_more():
    assert _agree(1.0, 1.5e-12 + 1.0)
    assert not _agree(1.0, 3e-12 + 1.0)


def test_as_float_widens_and_rejects():
    assert _as_float(Fraction(1, 4)) == 0.25
    with pytest.raises(NumError) as e:
        _as_float(RangeValue(1, 1, None))
    assert e.value.args[0] == NOT_A_NUMBER
    with pytest.raises(NumError) as big:
        _as_float(10**400)
    assert "too large" in big.value.args[0]


def test_fold_labels_map_ops_to_spellings():
    from adhoc.runtime import FOLD_LABELS

    assert FOLD_LABELS == {"add": "\\sum", "mul": "\\prod"}


# --- the symbolic closed-form tier (adhoc/symbolic.py) ---


import sympy

from adhoc.runtime import PRELUDE, Engine
from adhoc.span import Span
from adhoc.symbolic import Symbolic, classify
from adhoc.symbolic import E as E_SYM
from adhoc.symbolic import PI as PI_SYM


def sym(expr):
    """Admit a sympy expression through the tier's gate — the only route tests
    use to build symbolic values, mirroring what the seam does."""
    return classify(expr)


SQRT2 = sym(sympy.sqrt(2))
SQRT3 = sym(sympy.sqrt(3))


def test_symbolic_products_collapse_back_to_exact():
    # The tier's headline: √2·√2 recognizes and collapses to the exact integer 2;
    # π − π is 0. The collapse is an int, not a Fraction.
    product = nmul(SQRT2, SQRT2)
    assert product == 2 and type(product) is int
    assert nsub(PI_SYM, PI_SYM) == 0 and type(nsub(PI_SYM, PI_SYM)) is int


def test_symbolic_results_stay_symbolic():
    # √2·√3 is √6, √8 normalizes to 2√2 — same canonical form, structural eq.
    assert nmul(SQRT2, SQRT3) == sym(sympy.sqrt(6))
    assert sym(sympy.sqrt(8)) == sym(2 * sympy.sqrt(2))
    assert nadd(PI_SYM, PI_SYM) == sym(2 * sympy.pi)
    assert npow(2, Fraction(1, 2)) == SQRT2  # 2^(1/2) recognizes as √2
    assert npow(8, Fraction(1, 3)) == 2      # perfect cube collapses


def test_symbolic_display_is_truncated_digits_plus_ellipsis():
    assert nshow(PI_SYM) == "3.14159265358979..."
    assert nshow(E_SYM) == "2.71828182845905..."
    assert nshow(SQRT2) == "1.4142135623731..."
    assert nshow(ndiv(PI_SYM, 2)) == "1.5707963267949..."
    assert nshow(nmul(2, PI_SYM)) == "6.28318530717959..."
    assert nshow(nneg(PI_SYM)) == "-3.14159265358979..."


def test_symbolic_without_closed_form_falls_to_float():
    # The strict single-term shape: π + 1, π·√2, 1/π and 2^(1/3) have no
    # coefficient×atom form — the float tier stands in for the algebraic/RRA
    # tiers until they land.
    assert nadd(PI_SYM, 1) == 4.141592653589793
    assert nmul(PI_SYM, SQRT2) == 4.442882938158366
    assert ndiv(1, PI_SYM) == 0.3183098861837907
    assert npow(2, Fraction(1, 3)) == 1.2599210498948732
    assert npow(PI_SYM, -1) == 0.3183098861837907


def test_symbolic_exact_tier_domain_errors_are_typed():
    # No complex tier and no exact-tier infinity: fractional powers of negative
    # bases and 0⁻ⁿ are typed NumErrors (the float tier would yield NaN).
    with pytest.raises(NumError, match="not a real number"):
        npow(-2, Fraction(1, 2))
    with pytest.raises(NumError, match=DIVISION_BY_ZERO):
        npow(0, Fraction(-1, 2))


def test_symbolic_equality_is_exact():
    assert neq(PI_SYM, PI_SYM)
    assert neq(SQRT2, npow(2, Fraction(1, 2)))
    assert not neq(PI_SYM, Fraction(22, 7))  # an atom never equals a rational
    assert not neq(SQRT2, 2)


def test_symbolic_ordering_is_exact():
    eng = Engine({}, (Span(0, 0),))
    assert eng.lt(PI_SYM, Fraction(22, 7), 0)
    assert not eng.gt(PI_SYM, Fraction(22, 7), 0)
    assert eng.lt(SQRT2, Fraction(3, 2), 0)
    assert eng.gt(PI_SYM, 3, 0)
    assert eng.ge(sym(sympy.sqrt(2)), sym(sympy.sqrt(2)), 0)


def test_symbolic_float_side_compares_approximately():
    # A float operand drags the comparison to the float tier: π equals its own
    # double-precision rounding, and differs from 22/7's.
    assert neq(PI_SYM, 3.141592653589793)
    assert not neq(PI_SYM, 3.14)


def test_as_float_widens_symbolic_reals():
    assert _as_float(PI_SYM) == math.pi
    assert _as_float(SQRT2) == math.sqrt(2)


def test_prelude_constants_are_symbolic():
    assert PRELUDE["pi"] is PI_SYM
    assert PRELUDE["e"] is E_SYM
    assert isinstance(PRELUDE["pi"], Symbolic)


def test_prelude_builtins_recognize_exact_forms():
    assert PRELUDE["sqrt"](2) == SQRT2
    assert PRELUDE["sqrt"](8) == sym(2 * sympy.sqrt(2))
    assert PRELUDE["sqrt"](2.0) == math.sqrt(2.0)  # float tier untouched
    assert PRELUDE["sin"](ndiv(PI_SYM, 2)) == 1
    assert PRELUDE["tan"](ndiv(PI_SYM, 4)) == 1
    assert PRELUDE["cos"](ndiv(PI_SYM, 6)) == sym(sympy.sqrt(3) / 2)
    assert PRELUDE["ln"](2) == sym(sympy.log(2))
    assert PRELUDE["ln"](1) == 0
    assert PRELUDE["sin"](0) == 0
    assert PRELUDE["sin"](1) == math.sin(1)  # no closed form → float tier


def test_prelude_builtins_domain_errors():
    with pytest.raises(NumError, match="not a real number"):
        PRELUDE["sqrt"](-2)
    with pytest.raises(NumError, match="defined only for positive"):
        PRELUDE["ln"](0)
    with pytest.raises(NumError, match="odd multiples of pi/2"):
        PRELUDE["tan"](ndiv(PI_SYM, 2))


def test_prelude_builtin_display():
    assert nshow(PRELUDE["sqrt"]) == "<fn \\sqrt(x)>"


def test_to_ad_admits_recognized_sympy_values():
    assert _to_ad(sympy.sqrt(2)) == SQRT2
    assert _to_ad(sympy.pi) == PI_SYM
    assert _to_ad(sympy.Rational(1, 2)) == Fraction(1, 2)


def test_to_ad_rejects_unrecognized_sympy_values():
    with pytest.raises(NumError, match="cannot convert a returned Symbol"):
        _to_ad(sympy.Symbol("x"))
    with pytest.raises(NumError, match="cannot convert"):
        _to_ad(sympy.sqrt(2) + sympy.pi)  # real, but no single-atom form

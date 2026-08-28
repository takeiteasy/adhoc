"""Modules and imports: `\import` over ad source files and `\pyimport` over Python
module members (ticket-27 semantics — two forms, two targets, no module values and no
dotted attribute access in the grammar).

Ad-file imports evaluate each file once per session in a fresh root environment; the
session registry, base directory, and import chain ride on the Engine and are inherited
by every child frame. Fixtures use only single-character or `\`-sigiled names — any ad
source must.
"""

import pytest

from adhoc.driver import run_source
from adhoc.parser import ParseError, parse_program
from adhoc.runtime import EvalError

LIB = "r = 10; f(x) = x + r"


def make_lib(tmp_path, name="lib", text=LIB):
    path = tmp_path / f"{name}.ad"
    path.write_text(text)
    return name


def run_at(tmp_path, source, env=None, modules=None):
    return run_source(source, env if env is not None else {},
                      modules=modules if modules is not None else {},
                      base_dir=str(tmp_path))


# --- \import: ad source files ---


def test_import_binds_all_top_level_names(tmp_path):
    make_lib(tmp_path, text="r = 10; k ≡ 5; f(x) = x + r")
    env: dict = {}
    assert run_at(tmp_path, '\\import("lib"); f(5)', env) == ["= 15"]
    assert run_at(tmp_path, "r", env) == ["= 10"]
    assert run_at(tmp_path, "k", env) == ["= 5"]


def test_import_selective_binds_only_members(tmp_path):
    make_lib(tmp_path)
    env: dict = {}
    assert run_at(tmp_path, '\\import("lib": f)', env) == []
    assert run_at(tmp_path, "f(5)", env) == ["= 15"]
    with pytest.raises(EvalError, match="`r` is not bound"):
        run_at(tmp_path, "r", env)


def test_imported_function_reads_module_global_through_closure(tmp_path):
    # `r` exists only in the module environment; the imported f still reads it.
    make_lib(tmp_path)
    env: dict = {}
    run_at(tmp_path, '\\import("lib": f)', env)
    assert run_at(tmp_path, "f(5)", env) == ["= 15"]


def test_import_selective_missing_member(tmp_path):
    make_lib(tmp_path)
    with pytest.raises(EvalError, match="`g` is not defined in `lib`"):
        run_at(tmp_path, '\\import("lib": f, g)')


def test_import_duplicate_member_rejected(tmp_path):
    make_lib(tmp_path)
    with pytest.raises(EvalError, match="duplicate member"):
        run_at(tmp_path, '\\import("lib": f, f)')


def test_import_produces_no_output(tmp_path):
    make_lib(tmp_path)
    assert run_at(tmp_path, '\\import("lib")', {}) == []


def test_reimport_is_an_identity_noop(tmp_path):
    # The module evaluates once; a re-import re-copies the same cached values, so
    # identical bindings do not collide.
    make_lib(tmp_path)
    env: dict = {}
    mods: dict = {}
    run_at(tmp_path, '\\import("lib")', env, mods)
    assert run_at(tmp_path, '\\import("lib"); f(1)', env, mods) == ["= 11"]


def test_import_collision_after_rebinding(tmp_path):
    make_lib(tmp_path)
    env: dict = {}
    mods: dict = {}
    run_at(tmp_path, "\\f = 1", env)
    with pytest.raises(EvalError, match="is already bound"):
        run_at(tmp_path, '\\import("lib")', env, mods)


def test_import_into_call_frame_from_function_body(tmp_path):
    # Imports are legal wherever statements are, including function bodies; each call
    # re-binds from the cached module into the fresh call frame.
    make_lib(tmp_path)
    env: dict = {}
    assert run_at(tmp_path, 'g() = \\import("lib"); f(2)', env) == ["g = <fn g()>"]
    assert run_at(tmp_path, "g()", env) == ["= 12"]
    assert run_at(tmp_path, "g()", env) == ["= 12"]
    with pytest.raises(EvalError, match="`f` is not bound"):
        run_at(tmp_path, "f(1)", env)  # never escapes the call frame


def test_import_is_not_an_expression(tmp_path):
    make_lib(tmp_path)
    with pytest.raises(ParseError, match="statements, not expressions"):
        parse_program('(\\import("lib"); 1)')
    with pytest.raises(EvalError, match="`\\\\import` reads an ad file"):
        run_at(tmp_path, '1 + \\import("lib")')


def test_nested_imports_resolve_against_the_importing_file(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.ad").write_text("n = 42")
    (tmp_path / "sub" / "outer.ad").write_text('\\import("inner"); d = n + n')
    env: dict = {}
    # outer resolves inner relative to outer's own directory, and outer's top-level
    # import makes inner's bindings part of outer's top-level scope, transitively.
    assert run_at(tmp_path / "sub", '\\import("outer"); d; n', env, {}) == ["= 84", "= 42"]


def test_circular_import_is_a_typed_error(tmp_path):
    (tmp_path / "a.ad").write_text('\\import("b")')
    (tmp_path / "b.ad").write_text('\\import("a")')
    with pytest.raises(EvalError, match="circular import") as e:
        run_at(tmp_path, '\\import("a")', {}, {})
    assert "a.ad" in e.value.msg and "b.ad" in e.value.msg


def test_self_import_is_circular(tmp_path):
    (tmp_path / "solo.ad").write_text('\\import("solo")')
    with pytest.raises(EvalError, match="circular import"):
        run_at(tmp_path, '\\import("solo")')


def test_parse_error_inside_module_fails_at_import_span(tmp_path):
    (tmp_path / "broken.ad").write_text("x = ;")
    with pytest.raises(EvalError) as e:
        run_at(tmp_path, '\\import("broken")')
    assert "error in `broken`" in e.value.msg


def test_runtime_error_inside_module_fails_at_import_span(tmp_path):
    (tmp_path / "boom.ad").write_text("y = 1/0")
    with pytest.raises(EvalError) as e:
        run_at(tmp_path, '\\import("boom")')
    assert "error evaluating `boom`: division by zero" in e.value.msg


def test_missing_file_lists_searched_paths(tmp_path):
    with pytest.raises(EvalError) as e:
        run_at(tmp_path, '\\import("nowhere")')
    assert "no such ad file `nowhere.ad`" in e.value.msg
    assert str(tmp_path / "nowhere.ad") in e.value.msg


def test_python_module_name_hints_at_pyimport(tmp_path):
    with pytest.raises(EvalError) as e:
        run_at(tmp_path, '\\import("math")')
    assert "resolves to a Python module" in e.value.msg
    assert "\\pyimport" in e.value.msg


def test_import_resolves_against_working_directory(tmp_path, monkeypatch):
    # No base_dir (REPL shape): the CWD is searched.
    make_lib(tmp_path)
    monkeypatch.chdir(tmp_path)
    env: dict = {}
    assert run_source('\\import("lib"); f(5)', env) == ["= 15"]


def test_imports_are_scoped_to_their_session_registry(tmp_path):
    # A second session (fresh registry) re-evaluates from scratch: values are fresh
    # objects even though the source is identical.
    make_lib(tmp_path)
    env: dict = {}
    run_at(tmp_path, '\\import("lib")', env, {})
    other: dict = {}
    run_at(tmp_path, '\\import("lib")', other, {})
    assert env["f"] is not other["f"]


def test_module_const_does_not_join_importer_protected_set(tmp_path):
    # Protection-on-import is future work (ROADMAP): an imported const lands as an
    # ordinary binding, rebindable with `:=`.
    make_lib(tmp_path, text="k ≡ 5; f(x) = x")
    env: dict = {}
    run_at(tmp_path, '\\import("lib")', env)
    assert run_at(tmp_path, "k := 6; k", env) == ["k = 6", "= 6"]


# --- \pyimport: Python module members ---


def test_pyimport_binds_callable_and_value_members():
    env: dict = {}
    assert run_source('\\pyimport("math": \\hypot, \\tau)', env) == []
    assert run_source("\\hypot(3, 4)", env) == ["= 5.0"]
    assert run_source("\\tau", env) == ["= 6.283185307179586"]


def test_pyimport_callable_displays_as_py_callable():
    env: dict = {}
    run_source('\\pyimport("math": \\hypot)', env)
    assert run_source("\\hypot", env) == ["= <py math.hypot>"]


def test_pyimport_already_bound_name_rejects():
    env: dict = {}
    run_source("\\tau = 1", env)
    with pytest.raises(EvalError, match="`\\\\tau` is already bound"):
        run_source('\\pyimport("math": \\tau)', env)


def test_pyimport_prelude_collision_is_protection():
    with pytest.raises(EvalError, match="`\\\\pi` is a constant"):
        run_source('\\pyimport("math": \\pi)')


def test_pyimport_missing_member():
    with pytest.raises(EvalError, match="module `math` has no member `\\\\nosuch`"):
        run_source('\\pyimport("math": \\nosuch)')


def test_pyimport_unresolvable_module():
    with pytest.raises(EvalError, match="cannot resolve `no.such.mod`"):
        run_source('\\pyimport("no.such.mod": \\x)')


def test_pyimport_non_module_path():
    with pytest.raises(EvalError, match="`math.sqrt` is not a Python module"):
        run_source('\\pyimport("math.sqrt": \\x)')


def test_pyimport_unconvertible_member():
    with pytest.raises(EvalError, match="cannot convert a returned dict"):
        run_source('\\pyimport("sys": \\modules)')


def test_pyimport_duplicate_member():
    with pytest.raises(EvalError, match="duplicate member"):
        run_source('\\pyimport("math": \\tau, \\tau)')


def test_bare_pyimport_hints_at_member_form():
    with pytest.raises(EvalError) as e:
        run_source("\\pyimport")
    assert "binds Python members" in e.value.msg


def test_pyimport_requires_members_at_parse_time():
    with pytest.raises(ParseError, match="binds members by name"):
        parse_program('\\pyimport("math")')
    with pytest.raises(ParseError, match="string literal naming the module"):
        parse_program("\\pyimport(2)")


def test_pyimport_imported_names_are_ordinary_bindings():
    env: dict = {}
    run_source('\\pyimport("math": \\tau)', env)
    assert run_source("\\tau := 3; \\tau", env) == ["\\tau = 3", "= 3"]


# --- registry plumbing ---


def test_module_registry_holds_module_environments_by_path(tmp_path):
    make_lib(tmp_path)
    env: dict = {}
    mods: dict = {}
    run_at(tmp_path, '\\import("lib")', env, mods)
    assert len(mods) == 1
    (record,) = mods.values()
    assert record["f"](3) == 13

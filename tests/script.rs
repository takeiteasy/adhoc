//! Binary-level script-mode tests, run against the built `adhoc` binary via `adhoc run`.

use std::io::Write;
use std::process::Command;

fn write_script(name: &str, contents: &str) -> std::path::PathBuf {
    let path = std::env::temp_dir().join(name);
    let mut f = std::fs::File::create(&path).unwrap();
    f.write_all(contents.as_bytes()).unwrap();
    path
}

#[test]
fn script_runs_statement_by_statement_with_repl_style_output() {
    let path = write_script("adhoc_test_ok.ad", "x = 1 + 2;\n7\n");
    let out = Command::new(env!("CARGO_BIN_EXE_adhoc")).arg("run").arg(&path).output().unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8(out.stdout).unwrap();
    assert_eq!(stdout, "< x = 3\n< = 7\n");
}

#[test]
fn script_error_renders_with_line_gutter_and_exits_nonzero() {
    let path = write_script("adhoc_test_err.ad", "x = 1;\ny := 2\n");
    let out = Command::new(env!("CARGO_BIN_EXE_adhoc")).arg("run").arg(&path).output().unwrap();
    assert!(!out.status.success());
    let stdout = String::from_utf8(out.stdout).unwrap();
    // Multi-line source -> the `N: ` gutter is present, and the error stops the run after
    // the first (successful) statement rather than continuing past it.
    assert!(stdout.contains("< x = 1"));
    assert!(stdout.contains("2: y := 2"));
    assert!(!stdout.contains("< y ="));
}

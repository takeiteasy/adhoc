"""Tokenizer. Whitespace-insensitive except that a newline is a `Newline` token —
the statement separator: the parser treats it as a boundary where an expression is
complete and as whitespace where an operand is expected, inside parentheses and out
(docs/grammar.md). Single-character (ASCII or unicode) identifiers, `--` line
comments, and the `\\`-name convention: every language-defined name longer than one
character takes a `\\` sigil.

A `\\`-name is also the spelling for a user-defined multi-character identifier. Unknown
names therefore lex cleanly and fail at evaluation if they are not bound, just like a
single-character identifier.

Token spans are byte offsets (see span.py); token text is carried where meaningful (the
number literal's source text, a backslash name with its sigil stripped, a string
literal's raw contents).

Strings are full ad values (docs/grammar.md): they bind, concatenate with `+`, and appear
as call arguments or standalone comment-like statements. Inside a literal exactly four
escapes decode — `\"`, `\\`, `\n`, `\t` — and any other backslash pair is an error; a
literal may still span lines. An unterminated one raises `UnterminatedString`, which the
parser maps to `IncompleteInput` so the REPL offers a continuation prompt exactly like an
unclosed parenthesis.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from string import punctuation
from unicodedata import category

from .span import Span
from .syntax import ASCII_SUBSCRIPTS, SUBSCRIPTS, is_ascii_subscript_char


class LexError(Exception):
    def __init__(self, msg: str, span: Span):
        super().__init__(msg)
        self.msg = msg
        self.span = span


class UnterminatedString(LexError):
    """A string literal still open at end of input. A distinct type so the parser can
    raise `IncompleteInput` (REPL continuation) rather than a hard error."""


@dataclass(frozen=True)
class Token:
    span: Span

    @property
    def describe(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class Number(Token):
    text: str

    @property
    def describe(self) -> str:
        return "a number"


@dataclass(frozen=True)
class Str(Token):
    text: str

    @property
    def describe(self) -> str:
        return '`"…"`'


@dataclass(frozen=True)
class Ident(Token):
    """A one-letter name with an optional subscript run. `spelling` is the source text
    when it differs from the canonical `ch` (`x_1` for `x₁`)."""

    ch: str
    spelling: str | None = field(default=None, compare=False)

    @property
    def describe(self) -> str:
        return f"`{self.ch}`"


@dataclass(frozen=True)
class Backslash(Token):
    name: str

    @property
    def describe(self) -> str:
        return f"`\\{self.name}`"


@dataclass(frozen=True)
class Radical(Token):
    """The prefix radical operator `√` — the operator spelling of `\\sqrt(...)`.
    `√` is a math symbol, not a letter (`isalpha` is False), so it cannot lex as
    an identifier: it gets its own token and the parser gives it its prefix rule.
    Not a name — it cannot be aliased, bound, or shadowed."""

    @property
    def describe(self) -> str:
        return "`√`"


@dataclass(frozen=True)
class Superscript(Token):
    """A superscript exponent run (`²`, `⁻¹`, `ⁿ⁺¹`): sugar for `^`. `tokens` is the run
    transliterated to ASCII and tokenized, spans mapped back onto the glyphs, ending in
    `Eof`; the parser reads them as the exponent expression."""

    tokens: tuple[Token, ...]

    @property
    def describe(self) -> str:
        return "a superscript"


@dataclass(frozen=True)
class Delim(Token):
    """A delimiter glyph: `⌊ ⌋ ⌈ ⌉`, or a bar `|` / `‖` (`∥` reads as `‖`), which opens and
    closes alike. The parser rewrites a delimited expression to `\\floor`, `\\ceil`,
    `\\abs` or `\\norm`."""

    ch: str

    @property
    def describe(self) -> str:
        return f"`{self.ch}`"


@dataclass(frozen=True)
class NthRoot(Token):
    """The prefix radicals `∛` and `∜`; `index` is the root (3 or 4). Like `√`, not a
    name; the parser rewrites `∛x` to `\\root(x, 3)`."""

    ch: str
    index: int

    @property
    def describe(self) -> str:
        return f"`{self.ch}`"


@dataclass(frozen=True)
class Bang(Token):
    """Postfix factorial `!`."""

    @property
    def describe(self) -> str:
        return "`!`"


@dataclass(frozen=True)
class DoubleBang(Token):
    """Postfix double factorial: `‼`, or `!!` in ASCII."""

    @property
    def describe(self) -> str:
        return "`‼`"


@dataclass(frozen=True)
class Plus(Token):
    @property
    def describe(self) -> str:
        return "`+`"


@dataclass(frozen=True)
class Minus(Token):
    @property
    def describe(self) -> str:
        return "`-`"


@dataclass(frozen=True)
class Star(Token):
    @property
    def describe(self) -> str:
        return "`*`"


@dataclass(frozen=True)
class Slash(Token):
    @property
    def describe(self) -> str:
        return "`/`"


@dataclass(frozen=True)
class Caret(Token):
    @property
    def describe(self) -> str:
        return "`^`"


@dataclass(frozen=True)
class Eq(Token):
    @property
    def describe(self) -> str:
        return "`=`"


@dataclass(frozen=True)
class Less(Token):
    @property
    def describe(self) -> str:
        return "`<`"


@dataclass(frozen=True)
class LessEq(Token):
    @property
    def describe(self) -> str:
        return "`<=`"


@dataclass(frozen=True)
class Greater(Token):
    @property
    def describe(self) -> str:
        return "`>`"


@dataclass(frozen=True)
class GreaterEq(Token):
    @property
    def describe(self) -> str:
        return "`>=`"


@dataclass(frozen=True)
class Question(Token):
    """The ternary conditional's opening mark: `cond ? a : b` (docs/grammar.md).
    `:` closes it in expression position
    and keeps its import-only meaning everywhere else."""

    @property
    def describe(self) -> str:
        return "`?`"


@dataclass(frozen=True)
class Backtick(Token):
    @property
    def describe(self) -> str:
        return "backtick"


@dataclass(frozen=True)
class LParen(Token):
    @property
    def describe(self) -> str:
        return "`(`"


@dataclass(frozen=True)
class RParen(Token):
    @property
    def describe(self) -> str:
        return "`)`"


@dataclass(frozen=True)
class LBracket(Token):
    @property
    def describe(self) -> str:
        return "`[`"


@dataclass(frozen=True)
class RBracket(Token):
    @property
    def describe(self) -> str:
        return "`]`"


@dataclass(frozen=True)
class LAngle(Token):
    @property
    def describe(self) -> str:
        return "`⟨`"


@dataclass(frozen=True)
class RAngle(Token):
    @property
    def describe(self) -> str:
        return "`⟩`"


@dataclass(frozen=True)
class HashBracket(Token):
    """`#[`: the ASCII opener of an array literal, closed by `]`."""

    @property
    def describe(self) -> str:
        return "`#[`"


@dataclass(frozen=True)
class LBrace(Token):
    @property
    def describe(self) -> str:
        return "`{`"


@dataclass(frozen=True)
class RBrace(Token):
    @property
    def describe(self) -> str:
        return "`}`"


@dataclass(frozen=True)
class InfixOp(Token):
    """A unicode infix operator (set operators, `∘`, `≠`, `≈`); `name` is the canonical `\\`-name it shares with its
    ASCII spelling (`∪` is `\\cup`)."""

    name: str

    @property
    def describe(self) -> str:
        return f"`{_GLYPH_SYMBOLS[self.name]}`"


@dataclass(frozen=True)
class CustomOp(Token):
    ch: str

    @property
    def describe(self) -> str:
        return f"`{self.ch}`"


@dataclass(frozen=True)
class Prime(Token):
    """Postfix `'`, or `ᵀ` (`glyph`): transpose, and derivative on a function for `'` only."""

    glyph: str = "'"

    @property
    def describe(self) -> str:
        return f"`{self.glyph}`"


@dataclass(frozen=True)
class MapsTo(Token):
    """The lambda arrow `↦`, ASCII `->` or `\\mapsto`."""

    @property
    def describe(self) -> str:
        return "`↦`"


@dataclass(frozen=True)
class At(Token):
    """The contraction operator `@` (`\\contract` is its `\\`-name)."""

    @property
    def describe(self) -> str:
        return "`@`"


@dataclass(frozen=True)
class Placeholder(Token):
    """The partial-application hole: `·`, `⋅` or `_` (a `_` inside a `\\name` is part of
    it). `ch` is the spelling used, so diagnostics echo it."""

    ch: str

    @property
    def describe(self) -> str:
        return f"`{self.ch}`"


@dataclass(frozen=True)
class Semi(Token):
    @property
    def describe(self) -> str:
        return "`;`"


@dataclass(frozen=True)
class Newline(Token):
    """The statement separator, everywhere: the parser skips newline runs where an
    *operand* is expected (a statement or expression continues onto the next line
    mid-expression — `1 +` NL `2` is one sum, an argument may start on the line
    after its `,`), and a newline at a statement boundary separates. Inside `(...)`
    this makes a parenthesized group the multi-line statement form and lets argument
    lists span lines (docs/grammar.md)."""

    @property
    def describe(self) -> str:
        return "end of line"


@dataclass(frozen=True)
class Comma(Token):
    @property
    def describe(self) -> str:
        return "`,`"


@dataclass(frozen=True)
class Colon(Token):
    """The member-list separator in import statements: `\\import("lib": f, \\g)`.
    The only use of `:` — statement-level binding is `=`, force-reassignment does
    not exist."""

    @property
    def describe(self) -> str:
        return "`:`"


@dataclass(frozen=True)
class DotDot(Token):
    @property
    def describe(self) -> str:
        return "`..`"


@dataclass(frozen=True)
class Eof(Token):
    @property
    def describe(self) -> str:
        return "end of input"


_SINGLE_CHAR_TOKENS = {
    "`": Backtick,
    "+": Plus,
    "-": Minus,
    "*": Star,
    "/": Slash,
    "^": Caret,
    "=": Eq,
    "(": LParen,
    ")": RParen,
    ";": Semi,
    ",": Comma,
    "?": Question,
    "[": LBracket,
    "]": RBracket,
    "'": Prime,
    "@": At,
    "⟨": LAngle,
    "⟩": RAngle,
    "{": LBrace,
    "}": RBrace,
}

_INFIX_GLYPHS = {"∪": "cup", "∩": "cap", "∖": "setminus", "∈": "in", "⊆": "subseteq",
                  "≡": "equiv", "∘": "circ", "≠": "neq", "≈": "approx", "∉": "notin", "⊂": "subset",
                  "⊇": "supseteq", "⊃": "supset", "%": "mod", "∠": "angle",
                  "∧": "and", "∨": "or", "×": "times", "⊗": "otimes", "→": "implies", "↔": "iff", "¬": "not"}
_GLYPH_SYMBOLS = {name: symbol for symbol, name in _INFIX_GLYPHS.items()}

# `\\`-names that end in a digit; every other digit after a name is a number.
_DIGIT_NAMES = frozenset({"atan"})

_ROOT_INDEX = {"∛": 3, "∜": 4}

SUPERSCRIPTS = dict(zip(
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵁⱽᵂᵅᵝᵞᵟᵋᶿᵠᵡ",
    "0123456789+-()abcdefghijklmnoprstuvwxyzABDEGHIJKLMNOPRUVWαβγδεθφχ"))
_TRANSPOSE_GLYPH = "ᵀ"

DELIMITERS = {"⌊": "⌊", "⌋": "⌋", "⌈": "⌈", "⌉": "⌉", "|": "|", "‖": "‖", "∥": "‖"}

_STRING_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}


def _take_exponent(entries: list[tuple[int, str]], n: int, j: int) -> int:
    """Consume a float exponent (`e-3`, `E+6`, `e10`) at entry index `j`,
    returning the index past it. An `e`/`E` not followed by an optional sign
    and a digit is left alone — `2e` stays juxtaposition (`2*e`), never a
    broken float."""
    if j < n and entries[j][1] in "eE":
        k = j + 1
        if k < n and entries[k][1] in "+-":
            k += 1
        if k < n and entries[k][1].isascii() and entries[k][1].isdigit():
            k += 1
            while k < n and entries[k][1].isascii() and entries[k][1].isdigit():
                k += 1
            return k
    return j


def _superscript_tokens(entries: list[tuple[int, str]], first: int, last: int,
                       text: str) -> tuple[Token, ...]:
    """Tokenize the ASCII form of the superscript run `entries[first:last]`, mapping
    each token's span back onto the glyphs it came from."""
    def glyph_end(k: int) -> int:
        return entries[k][0] + len(entries[k][1].encode("utf-8"))

    mapped = []
    for tok in tokenize(text):
        if isinstance(tok, Eof):
            end = glyph_end(last - 1)
            mapped.append(Eof(span=Span.point(end)))
        else:
            mapped.append(replace(tok, span=Span(entries[first + tok.span.start][0],
                                                 glyph_end(first + tok.span.end - 1))))
    return tuple(mapped)


def _scan(src: str, entries: list[tuple[int, str]], start: int,
          spellings: dict[str, tuple[str, ...]], declaration: bool = False) -> Iterator[Token]:
    """Tokenize source text. Token spans are byte offsets; entries carry (byte_off, char)
    pairs so scanning walks code points while spans stay in bytes."""
    n = len(entries)
    eof_off = entries[-1][0] + len(entries[-1][1].encode("utf-8")) if entries else 0
    i = start

    while i < n:
        pos, c = entries[i]

        if c == "\n":
            yield Newline(span=Span(pos, pos + 1))
            i += 1
            continue

        if c.isspace():
            i += 1
            continue

        if declaration:
            declaration = False
            if c in punctuation and c not in "(),;\\":
                j = i + 1
                while j < n and entries[j][1] in punctuation and entries[j][1] not in "(),;\\":
                    j += 1
                end = entries[j][0] if j < n else eof_off
                yield CustomOp(ch=src[i:j], span=Span(pos, end))
                i = j
                continue

        spelling = next((op for op in spellings.get(c, ()) if src.startswith(op, i)), None)
        if spelling is not None:
            end = entries[i + len(spelling)][0] if i + len(spelling) < n else eof_off
            yield CustomOp(ch=spelling, span=Span(pos, end))
            i += len(spelling)
            continue

        if c == "-" and i + 1 < n and entries[i + 1][1] == "-":
            i += 2
            while i < n and entries[i][1] != "\n":
                i += 1
            continue

        if c == "↦" or (c == "-" and i + 1 < n and entries[i + 1][1] == ">"):
            width = 1 if c == "↦" else 2
            end = entries[i + width][0] if i + width < n else eof_off
            yield MapsTo(span=Span(pos, end))
            i += width
            continue

        if c == '"':
            # Exactly four escapes decode inside a literal (`\"`, `\\`, `\n`, `\t`);
            # any other backslash pair is an error. The span stays over the raw source
            # bytes — backslashes included — while `text` carries the decoded value.
            j = i + 1
            parts: list[str] = []
            while j < n and entries[j][1] != '"':
                ch = entries[j][1]
                if ch != "\\":
                    parts.append(ch)
                    j += 1
                    continue
                if j + 1 >= n:
                    raise UnterminatedString(
                        "unterminated string literal", Span(pos, eof_off)
                    )
                esc = entries[j + 1][1]
                decoded = _STRING_ESCAPES.get(esc)
                if decoded is None:
                    raise LexError(
                        f"unknown string escape `\\{esc}`",
                        Span(entries[j][0], entries[j][0] + 1 + len(esc.encode("utf-8"))),
                    )
                parts.append(decoded)
                j += 2
            end = entries[j][0] + 1 if j < n else eof_off
            span = Span(pos, end)
            if j >= n:
                raise UnterminatedString("unterminated string literal", span)
            yield Str(text="".join(parts), span=span)
            i = j + 1
            continue

        if c.isascii() and c.isdigit():
            j = i
            while j < n and entries[j][1].isascii() and entries[j][1].isdigit():
                j += 1
            # A `.` with a digit after it is the fractional part (`3.14`, exact);
            # a `.` with no digit after it is the explicit float marker (`1.`,
            # the float 1.0) — unless a second dot follows, which is the range
            # operator (`1..10` stays `1` + `..`).
            if j < n and entries[j][1] == ".":
                if (j + 1 < n and entries[j + 1][1].isascii()
                        and entries[j + 1][1].isdigit()):
                    j += 1
                    while j < n and entries[j][1].isascii() and entries[j][1].isdigit():
                        j += 1
                elif not (j + 1 < n and entries[j + 1][1] == "."):
                    j += 1
            j = _take_exponent(entries, n, j)
            end = entries[j][0] if j < n else eof_off
            yield Number(text=src[i:j], span=Span(pos, end))
            i = j
            continue

        if (c == "." and i + 1 < n and entries[i + 1][1].isascii()
                and entries[i + 1][1].isdigit()):
            # A leading-dot decimal (`.5`): exact, like every other dotted
            # literal. A `.` followed by another `.` is still the range
            # operator — that shape cannot reach this branch (not a digit).
            j = i + 1
            while j < n and entries[j][1].isascii() and entries[j][1].isdigit():
                j += 1
            j = _take_exponent(entries, n, j)
            end = entries[j][0] if j < n else eof_off
            yield Number(text=src[i:j], span=Span(pos, end))
            i = j
            continue

        if c == "\\":
            j = i + 1
            # Underscores join multi-character names (`\rel_tol`, `\my_var`): a `_`
            # continues a name but cannot start one — a bare `_` is still an
            # unexpected character.
            while j < n and (entries[j][1].isalpha() or entries[j][1] == "_"):
                j += 1
            name = src[i + 1 : j]
            if name in _DIGIT_NAMES and j < n and entries[j][1] == "2" \
                    and not (j + 1 < n and entries[j + 1][1].isalnum()):
                name += "2"
                j += 1
            end = entries[j][0] if j < n else eof_off
            span = Span(pos, end)
            if not name:
                raise LexError("bare `\\` with no name following", span)
            if name == "mapsto":
                yield MapsTo(span=span)
            else:
                yield Backslash(name=name, span=span)
            i = j
            continue

        if c in SUPERSCRIPTS:
            j = i
            while j < n and entries[j][1] in SUPERSCRIPTS:
                j += 1
            end = entries[j][0] if j < n else eof_off
            text = "".join(SUPERSCRIPTS[entries[k][1]] for k in range(i, j))
            if not any(ch.isalnum() for ch in text):
                raise LexError("a superscript needs digits or letters", Span(pos, end))
            yield Superscript(tokens=_superscript_tokens(entries, i, j, text),
                                      span=Span(pos, end))
            i = j
            continue

        if c in SUBSCRIPTS:
            raise LexError(f"subscript `{c}` needs a letter before it",
                           Span(pos, pos + len(c.encode("utf-8"))))

        if c == _TRANSPOSE_GLYPH:
            yield Prime(glyph=c, span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c in "∅∀∃∫∂":
            yield Ident(ch=c, span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c.isalpha():
            j = i + 1
            while j < n and entries[j][1] in SUBSCRIPTS:
                j += 1
            name = src[i:j]
            spelling = None
            # ASCII subscript: `x_1`, `x_ij`, `x_b`. A `_` with no alphanumeric after it stays
            # the placeholder. The canonical name uses glyphs when every character has one.
            if j == i + 1 and j + 1 < n and entries[j][1] == "_" \
                    and is_ascii_subscript_char(entries[j + 1][1]):
                k = j + 1
                while k < n and is_ascii_subscript_char(entries[k][1]):
                    k += 1
                run = "".join(entries[m][1] for m in range(j + 1, k))
                spelling = src[i:k]
                name = (c + "".join(ASCII_SUBSCRIPTS[ch] for ch in run)
                        if all(ch in ASCII_SUBSCRIPTS for ch in run) else spelling)
                j = k
            end = entries[j][0] if j < n else eof_off
            yield Ident(ch=name, spelling=spelling, span=Span(pos, end))
            i = j
            continue

        if c in _ROOT_INDEX:
            yield NthRoot(ch=c, index=_ROOT_INDEX[c],
                                  span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c == "!":
            if i + 1 < n and entries[i + 1][1] == "=":
                raise LexError("`!=` is not an operator; use `≠` or `\\neq`",
                               Span(pos, entries[i + 1][0] + 1))
            if i + 1 < n and entries[i + 1][1] == "!":
                yield DoubleBang(span=Span(pos, entries[i + 1][0] + 1))
                i += 2
            else:
                yield Bang(span=Span(pos, pos + 1))
                i += 1
            continue

        if c == "‼":
            yield DoubleBang(span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c == "√":
            # The radical: a math symbol (not `isalpha`), so it is its own token —
            # the parser's prefix rule rewrites it to a `\sqrt(...)` application.
            end = pos + len(c.encode("utf-8"))
            yield Radical(span=Span(pos, end))
            i += 1
            continue

        if c in DELIMITERS:
            yield Delim(ch=DELIMITERS[c], span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c in _INFIX_GLYPHS:
            end = pos + len(c.encode("utf-8"))
            yield InfixOp(name=_INFIX_GLYPHS[c], span=Span(pos, end))
            i += 1
            continue

        if c == "#" and i + 1 < n and entries[i + 1][1] == "[":
            yield HashBracket(span=Span(pos, entries[i + 1][0] + 1))
            i += 2
            continue

        if c == ":":
            # The only use of `:` is the import member-list separator; statement-level
            # binding is plain `=`.
            end = pos + len(c.encode("utf-8"))
            yield Colon(span=Span(pos, end))
            i += 1
            continue

        if c == "." and i + 1 < n and entries[i + 1][1] == ".":
            yield DotDot(span=Span(pos, entries[i + 1][0] + 1))
            i += 2
            continue

        if c in "≤≥":
            cls = LessEq if c == "≤" else GreaterEq
            yield cls(span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        if c in "<>":
            if i + 1 < n and entries[i + 1][1] == "=":
                cls = LessEq if c == "<" else GreaterEq
                yield cls(span=Span(pos, entries[i + 1][0] + 1))
                i += 2
                continue
            cls = Less if c == "<" else Greater
            yield cls(span=Span(pos, pos + 1))
            i += 1
            continue

        if c in "·⋅_":
            yield Placeholder(ch=c, span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        cls = _SINGLE_CHAR_TOKENS.get(c)
        if cls is not None:
            end = pos + len(c.encode("utf-8"))
            yield cls(span=Span(pos, end))
            i += 1
            continue

        if c in "&~" or (not c.isascii() and category(c) == "Sm"):
            yield CustomOp(ch=c, span=Span(pos, pos + len(c.encode("utf-8"))))
            i += 1
            continue

        raise LexError(
            f"unexpected character `{c}`", Span(pos, pos + len(c.encode("utf-8")))
        )

    yield Eof(span=Span.point(eof_off))


PUNCTUATION_OPERATORS = frozenset("+-*/^%@<>&~")
_RESERVED_PUNCTUATION = frozenset("+-*/^%@<>") | {"<=", ">=", "--", "->"}


def is_punctuation_operator(spelling: str) -> bool:
    return (bool(spelling) and all(ch in PUNCTUATION_OPERATORS for ch in spelling)
            and spelling not in _RESERVED_PUNCTUATION
            and "--" not in spelling and "->" not in spelling)


def _entries(src: str) -> list[tuple[int, str]]:
    entries = []
    offset = 0
    for ch in src:
        entries.append((offset, ch))
        offset += len(ch.encode("utf-8"))
    return entries


def _punctuation_spellings(operators: Iterable[str]) -> dict[str, tuple[str, ...]]:
    groups: dict[str, list[str]] = {}
    for spelling in operators:
        if is_punctuation_operator(spelling):
            groups.setdefault(spelling[0], []).append(spelling)
    return {first: tuple(sorted(group, key=len, reverse=True))
            for first, group in groups.items()}


def tokenize(src: str, operators: Iterable[str] = ()) -> list[Token]:
    """Return tokens with byte spans, matching the longest declared punctuation spelling."""
    return list(_scan(src, _entries(src), 0, _punctuation_spellings(operators)))


class TokenBuffer:
    """Cache lookahead and rewind unread source when the operator registry changes."""

    def __init__(self, source: str):
        self.source = source
        self.entries = _entries(source)
        self.offsets = {offset: index for index, (offset, _) in enumerate(self.entries)}
        self.offsets[len(source.encode("utf-8"))] = len(self.entries)
        self.operators: Iterable[str] = ()
        self.tokens: list[Token] = []
        self.reset(0)

    def reset(self, index: int, *, declaration: bool = False) -> None:
        offset = self.tokens[index - 1].span.end if index else 0
        del self.tokens[index:]
        self.scanner = _scan(self.source, self.entries, self.offsets[offset],
                             _punctuation_spellings(self.operators), declaration)

    def __getitem__(self, index: int) -> Token:
        while index >= len(self.tokens) and (not self.tokens or not isinstance(self.tokens[-1], Eof)):
            self.tokens.append(next(self.scanner))
        return self.tokens[min(index, len(self.tokens) - 1)]

    def from_index(self, index: int) -> Iterator[tuple[int, Token]]:
        while True:
            token = self[index]
            yield index, token
            if isinstance(token, Eof):
                break
            index += 1

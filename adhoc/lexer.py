"""Tokenizer. Whitespace-insensitive, single-character (ASCII or unicode) identifiers,
`--` line comments, and the `\\`-name convention: every language-defined name longer than
one character takes a `\\` sigil.

A `\\`-token always lexes cleanly if the name is in KNOWN_BACKSLASH_NAMES and fails, if at
all, at eval time as an unbound name — not at the lexer as an unknown token. Unrecognized
`\\`-names remain a lex error, which is what catches typos.

Token spans are byte offsets (see span.py); token text is carried where meaningful (the
number literal's source text, a backslash name with its sigil stripped, a string
literal's raw contents).

Strings are literals, not values (docs/grammar.md): they appear as `\\py` arguments or as
standalone statements (ignored, comment-like). The scanner keeps them escape-free — the
literal ends at the next `"`, whatever it contains — and an unterminated one raises
`UnterminatedString`, which the parser maps to `IncompleteInput` so the REPL offers a
continuation prompt exactly like an unclosed parenthesis.
"""

from dataclasses import dataclass

from .span import Span

KNOWN_BACKSLASH_NAMES = (
    "pi", "sum", "prod", "sqrt", "cup", "cap", "in", "subseteq", "setminus", "circ", "lim",
    "const", "arr", "expr", "if", "otherwise", "sin", "cos", "tan", "ln", "solve", "simplify",
    "expand", "factor", "eval", "body", "map", "fold", "filter", "graph", "infix", "and", "or",
    "not", "py",
)


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
    ch: str

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
class ColonEq(Token):
    @property
    def describe(self) -> str:
        return "`:=`"


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
class Semi(Token):
    @property
    def describe(self) -> str:
        return "`;`"


@dataclass(frozen=True)
class Comma(Token):
    @property
    def describe(self) -> str:
        return "`,`"


@dataclass(frozen=True)
class Eof(Token):
    @property
    def describe(self) -> str:
        return "end of input"


_SINGLE_CHAR_TOKENS = {
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
}


def tokenize(src: str) -> list[Token]:
    """Tokenize source text. Token spans are byte offsets; entries carry (byte_off, char)
    pairs so scanning walks code points while spans stay in bytes."""
    entries: list[tuple[int, str]] = []
    off = 0
    for ch in src:
        entries.append((off, ch))
        off += len(ch.encode("utf-8"))
    n = len(entries)
    eof_off = len(src.encode("utf-8"))
    tokens: list[Token] = []
    i = 0

    while i < n:
        pos, c = entries[i]

        if c.isspace():
            i += 1
            continue

        if c == "-" and i + 1 < n and entries[i + 1][1] == "-":
            i += 2
            while i < n and entries[i][1] != "\n":
                i += 1
            continue

        if c == '"':
            # Escape-free: the literal ends at the next `"`, whatever it contains.
            j = i + 1
            while j < n and entries[j][1] != '"':
                j += 1
            end = entries[j][0] + 1 if j < n else eof_off
            span = Span(pos, end)
            if j >= n:
                raise UnterminatedString("unterminated string literal", span)
            tokens.append(Str(text=src[i + 1 : j], span=span))
            i = j + 1
            continue

        if c.isascii() and c.isdigit():
            j = i
            while j < n and entries[j][1].isascii() and entries[j][1].isdigit():
                j += 1
            # Only consume `.` if a digit follows — `1.` lexes as `1` then errors on `.`.
            if (
                j < n
                and entries[j][1] == "."
                and j + 1 < n
                and entries[j + 1][1].isascii()
                and entries[j + 1][1].isdigit()
            ):
                j += 1
                while j < n and entries[j][1].isascii() and entries[j][1].isdigit():
                    j += 1
            end = entries[j][0] if j < n else eof_off
            tokens.append(Number(text=src[i:j], span=Span(pos, end)))
            i = j
            continue

        if c == "\\":
            j = i + 1
            while j < n and entries[j][1].isalpha():
                j += 1
            end = entries[j][0] if j < n else eof_off
            name = src[i + 1 : j]
            span = Span(pos, end)
            if not name:
                raise LexError("bare `\\` with no name following", span)
            if name not in KNOWN_BACKSLASH_NAMES:
                raise LexError(f"unknown \\-name `\\{name}`", span)
            tokens.append(Backslash(name=name, span=span))
            i = j
            continue

        if c.isalpha():
            end = pos + len(c.encode("utf-8"))
            tokens.append(Ident(ch=c, span=Span(pos, end)))
            i += 1
            continue

        if c == ":":
            if i + 1 < n and entries[i + 1][1] == "=":
                end = entries[i + 1][0] + 1
                tokens.append(ColonEq(span=Span(pos, end)))
                i += 2
                continue
            raise LexError("unexpected character `:`", Span(pos, pos + len(c.encode("utf-8"))))

        if c in "<>":
            if i + 1 < n and entries[i + 1][1] == "=":
                cls = LessEq if c == "<" else GreaterEq
                tokens.append(cls(span=Span(pos, entries[i + 1][0] + 1)))
                i += 2
                continue
            cls = Less if c == "<" else Greater
            tokens.append(cls(span=Span(pos, pos + 1)))
            i += 1
            continue

        cls = _SINGLE_CHAR_TOKENS.get(c)
        if cls is not None:
            end = pos + len(c.encode("utf-8"))
            tokens.append(cls(span=Span(pos, end)))
            i += 1
            continue

        raise LexError(
            f"unexpected character `{c}`", Span(pos, pos + len(c.encode("utf-8")))
        )

    tokens.append(Eof(span=Span.point(eof_off)))
    return tokens

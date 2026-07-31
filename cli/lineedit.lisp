;;;; lineedit.lisp
;;;;
;;;; In-process line editing and history via cl-readline (ticket 32), replacing the `rlwrap`
;;;; wrapper (ticket 29) as the primary path when adhoc/cli's own build has libreadline
;;;; available. Confined to adhoc/cli -- adhoc/repl, and therefore adhoc/tests which depends
;;;; on it, stays free of the cl-readline/libreadline dependency. See docs/architecture.md.
;;;;
;;;; Fd 0 invariant: cl-readline's readline() reads file descriptor 0 directly in C, bypassing
;;;; any Lisp stream wrapped around it. A session must pick exactly one reader for its whole
;;;; run -- readline-read-line below always calls rl:readline and never touches its STREAM
;;;; argument, so once main.lisp decides to use it as run-repl's read-line-fn, the
;;;; *standard-input* fd-stream cli.lisp built for UTF-8 output framing is simply never read
;;;; from again.

(in-package #:adhoc/cli)

(defun %history-file ()
  "A function, not a top-level defvar: this is a dumped image, so a defvar's initform runs
once at `ros build` time and would freeze in the build machine's $ADHOC_HISTORY (or lack of
one) forever, rather than each invocation's. Same default path bin/adhoc has always passed
to `rlwrap -H`, so history carries over regardless of which of the two editors ends up
handling a given session."
  (or (uiop:getenv "ADHOC_HISTORY")
      (namestring (merge-pathnames ".adhoc_history" (user-homedir-pathname)))))

#+sbcl
(cffi:defcfun ("setlocale" %c-setlocale) :string
  (category :int) (locale :string))

(defparameter +lc-all+ 6
  "LC_ALL's value in both macOS's and glibc's <locale.h>.")

(defun %readline-requested-p ()
  "False when ADHOC_NO_READLINE is set -- the escape hatch bin/adhoc's rlwrap fallback
exports so the two editors never both try to read fd 0 (see docs/architecture.md)."
  (not (uiop:getenv "ADHOC_NO_READLINE")))

(defun %stdin-tty-p ()
  #+sbcl (plusp (sb-unix:unix-isatty 0))
  #-sbcl nil)

(defun init-readline ()
  "Locale and history setup, called once before the REPL loop starts if readline is going to
be used. Never signals -- any failure here (unwritable history file, locale not installed,
...) just means the caller should fall back to plain read-line rather than abort startup."
  (handler-case
      (progn
        ;; Without this, readline's line editing operates byte-at-a-time in the C locale,
        ;; and a multi-byte UTF-8 identifier like `\pi`'s single-character form `π`
        ;; renders as mangled bytes instead of one character -- see docs/grammar.md on
        ;; unicode identifiers.
        (%c-setlocale +lc-all+ "")
        (let ((history-file (%history-file)))
          (when (probe-file history-file)
            (rl:read-history history-file)))
        t)
    (error () nil)))

(defun readline-available-p ()
  "Whether this session should use in-process readline: requested (not opted out), an
interactive tty (piped input -- tests, scripts -- never engages it), and init succeeded."
  (and (%readline-requested-p) (%stdin-tty-p) (init-readline)))

(defun save-history ()
  (ignore-errors (rl:write-history (%history-file))))

(defun readline-read-line (stream prompt)
  "A run-repl READ-LINE-FN: read one line via cl-readline. STREAM is ignored -- see the fd 0
invariant above. PROMPT is passed through with :already-prompted, since run-repl has already
written it to *standard-output* itself; readline still needs the text to redraw correctly
after in-line edits, history recall, etc."
  (declare (ignore stream))
  (or (rl:readline :prompt prompt :already-prompted t :add-history t) :eof))

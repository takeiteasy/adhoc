;;;; lexer.lisp
;;;;
;;;; Lexer for phase-0 `ad`. Whitespace-insensitive, unicode-aware. See docs/grammar.md.

(in-package #:adhoc/ad)

(define-condition ad-error (error)
  ((message :initarg :message :reader ad-error-message)
   (start :initarg :start :reader ad-error-start)
   (end :initarg :end :reader ad-error-end))
  (:report (lambda (c stream)
             (format stream "~a" (ad-error-message c)))))

(define-condition ad-lex-error (ad-error) ()
  (:report (lambda (c stream)
             (format stream "LEX ERROR: ~a" (ad-error-message c)))))

(define-condition ad-parse-error (ad-error) ()
  (:report (lambda (c stream)
             (format stream "PARSE ERROR: ~a" (ad-error-message c)))))

;; A subclass of ad-parse-error, not a sibling: signalled instead of ad-parse-error
;; specifically when the unexpected token is :eof, meaning the input just ran out mid-
;; expression rather than containing something actually wrong (`(1 + 2`, `1 +`, `2 ^`, `x =`).
;; A subclass keeps every existing `(adhoc/ad:ad-parse-error (e) ...)` handler working
;; unchanged -- callers that want to offer a continuation prompt catch this more specific
;; condition first.
(define-condition ad-incomplete-input (ad-parse-error) ()
  (:report (lambda (c stream)
             (format stream "PARSE ERROR: ~a" (ad-error-message c)))))

(defstruct (token (:constructor make-token (kind text start end)))
  "kind is one of :number :ident :backslash :plus :minus :star :slash :caret :eq :coloneq
:lparen :rparen :semi :eof.

text holds the literal text (number as written, the single identifier character as a
one-char string, or the bare name after `\\` for :backslash tokens).

start/end are 0-based half-open character offsets `[start, end)` into the source; a
`\\`-token's span covers the sigil. :eof is a zero-width span at the end of the source."
  kind text start end)

;; The complete set of `\`-names the language knows about (see docs/grammar.md and
;; docs/language.md). Phase 0 binds none of them, but seeding the full table now means a
;; `\`-token always lexes cleanly and fails, if at all, at eval time as an unbound name --
;; not at the lexer as an unknown token. Unrecognized `\`-names remain a lex error, which is
;; what catches typos.
(defparameter *known-backslash-names*
  '("pi" "sum" "prod" "sqrt" "cup" "cap" "in" "subseteq" "setminus" "circ"
    "lim" "const" "arr" "expr" "if" "otherwise" "sin" "cos" "tan" "ln"
    "solve" "simplify" "expand" "factor" "eval" "body" "map" "fold" "filter"
    "graph" "infix" "and" "or" "not"))

(defun tokenize (src)
  (let* ((chars (coerce src 'simple-vector))
         (n (length chars))
         (i 0)
         (tokens '()))
    (labels ((cur () (aref chars i))
             (ident-char-p (c) (alpha-char-p c))
             (push-tok (kind text start end) (push (make-token kind text start end) tokens)))
      (loop while (< i n) do
        (let ((c (cur)))
          (cond
            ((member c '(#\Space #\Tab #\Newline #\Return #\Linefeed #\Page) :test #'char=)
             (incf i))
            ((and (char= c #\-) (< (1+ i) n) (char= (aref chars (1+ i)) #\-))
             (loop while (and (< i n) (char/= (aref chars i) #\Newline)) do (incf i)))
            ((digit-char-p c)
             (let ((pos i) (j i))
               (loop while (and (< j n) (digit-char-p (aref chars j))) do (incf j))
               (when (and (< j n) (char= (aref chars j) #\.)
                          (< (1+ j) n) (digit-char-p (aref chars (1+ j))))
                 (incf j)
                 (loop while (and (< j n) (digit-char-p (aref chars j))) do (incf j)))
               (push-tok :number (coerce (subseq chars i j) 'string) pos j)
               (setf i j)))
            ((char= c #\\)
             (let ((pos i) (j (1+ i)))
               (loop while (and (< j n) (alpha-char-p (aref chars j))) do (incf j))
               (let ((name (coerce (subseq chars (1+ i) j) 'string)))
                 (when (zerop (length name))
                   (error 'ad-lex-error :message "bare `\\` with no name following" :start pos :end j))
                 (unless (member name *known-backslash-names* :test #'string=)
                   (error 'ad-lex-error :message (format nil "unknown \\-name `\\~a`" name) :start pos :end j))
                 (push-tok :backslash name pos j)
                 (setf i j))))
            ((ident-char-p c)
             (push-tok :ident (string c) i (1+ i))
             (incf i))
            ((and (char= c #\:) (< (1+ i) n) (char= (aref chars (1+ i)) #\=))
             (push-tok :coloneq ":=" i (+ i 2))
             (incf i 2))
            (t
             (let ((kind (case c
                           (#\+ :plus) (#\- :minus) (#\* :star) (#\/ :slash)
                           (#\^ :caret) (#\= :eq) (#\( :lparen) (#\) :rparen)
                           (#\; :semi) (t nil))))
               (unless kind
                 (error 'ad-lex-error :message (format nil "unexpected character `~a`" c) :start i :end (1+ i)))
               (push-tok kind (string c) i (1+ i))
               (incf i))))))
      (push-tok :eof "" n n)
      (nreverse tokens))))

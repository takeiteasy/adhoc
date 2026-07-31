;;;; lexer.lisp
;;;;
;;;; Lexer for phase-0 `ad`. Whitespace-insensitive, unicode-aware. See docs/grammar.md.

(in-package #:adhoc/ad)

(define-condition ad-error (error)
  ((message :initarg :message :reader ad-error-message)
   (pos :initarg :pos :reader ad-error-pos))
  (:report (lambda (c stream)
             (format stream "~a at column ~a" (ad-error-message c) (ad-error-pos c)))))

(define-condition ad-lex-error (ad-error) ()
  (:report (lambda (c stream)
             (format stream "LEX ERROR at column ~a: ~a" (ad-error-pos c) (ad-error-message c)))))

(define-condition ad-parse-error (ad-error) ()
  (:report (lambda (c stream)
             (format stream "PARSE ERROR at column ~a: ~a" (ad-error-pos c) (ad-error-message c)))))

(defstruct (token (:constructor make-token (kind text pos)))
  "kind is one of :number :ident :backslash :plus :minus :star :slash :caret :eq :coloneq
:lparen :rparen :semi :eof.

text holds the literal text (number as written, the single identifier character as a
one-char string, or the bare name after `\\` for :backslash tokens)."
  kind text pos)

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
             (push-tok (kind text pos) (push (make-token kind text pos) tokens)))
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
               (push-tok :number (coerce (subseq chars i j) 'string) (1+ pos))
               (setf i j)))
            ((char= c #\\)
             (let ((pos i) (j (1+ i)))
               (loop while (and (< j n) (alpha-char-p (aref chars j))) do (incf j))
               (let ((name (coerce (subseq chars (1+ i) j) 'string)))
                 (when (zerop (length name))
                   (error 'ad-lex-error :message "bare `\\` with no name following" :pos (1+ pos)))
                 (unless (member name *known-backslash-names* :test #'string=)
                   (error 'ad-lex-error :message (format nil "unknown \\-name `\\~a`" name) :pos (1+ pos)))
                 (push-tok :backslash name (1+ pos))
                 (setf i j))))
            ((ident-char-p c)
             (push-tok :ident (string c) (1+ i))
             (incf i))
            ((and (char= c #\:) (< (1+ i) n) (char= (aref chars (1+ i)) #\=))
             (push-tok :coloneq ":=" (1+ i))
             (incf i 2))
            (t
             (let ((kind (case c
                           (#\+ :plus) (#\- :minus) (#\* :star) (#\/ :slash)
                           (#\^ :caret) (#\= :eq) (#\( :lparen) (#\) :rparen)
                           (#\; :semi) (t nil))))
               (unless kind
                 (error 'ad-lex-error :message (format nil "unexpected character `~a`" c) :pos (1+ i)))
               (push-tok kind (string c) (1+ i))
               (incf i))))))
      (push-tok :eof "" (1+ n))
      (nreverse tokens))))

;;;; parser.lisp
;;;;
;;;; Precedence-climbing parser for phase-0 `ad`, over the grammar in docs/grammar.md.

(in-package #:adhoc/ad)

;; Per-node source spans (ticket 31), kept as an `eq` side table rather than a slot on the
;; AST nodes -- see ad/ast.lisp on why the node shape stays plain s-expression data. Bound
;; fresh by parse-program and returned as its second value; register-span! is called at each
;; make-* call site (not "on the way out" of a parse-X! function), since parse-atom!'s
;; :lparen branch returns its inner node unchanged and would otherwise clobber that node's
;; own span with the paren-inclusive one.
(defvar *node-spans*)

(defun register-span! (node start end)
  (setf (gethash node *node-spans*) (cons start end))
  node)

(defun node-span (node spans)
  "Return (values start end) for NODE in SPANS, or NIL if it has none registered."
  (let ((span (gethash node spans)))
    (if span (values (car span) (cdr span)) nil)))

(defstruct (token-stream (:constructor make-token-stream (tokens &optional (pos 0))))
  tokens pos)

(defun ts-peek (ts &optional (offset 0))
  (let ((tokens (token-stream-tokens ts)))
    (nth (min (+ (token-stream-pos ts) offset) (1- (length tokens))) tokens)))

(defun ts-prev-end (ts)
  "The end offset of the token just consumed -- used to build a left-nested bin-op's span,
which starts at its lhs's start (already known) and ends where the just-consumed rhs ended."
  (token-end (nth (max 0 (1- (token-stream-pos ts))) (token-stream-tokens ts))))

(defun ts-consume! (ts)
  (let ((tok (ts-peek ts)))
    (incf (token-stream-pos ts))
    tok))

(defun ts-expect! (ts kind)
  (let ((tok (ts-peek ts)))
    (unless (eq (token-kind tok) kind)
      (if (eq (token-kind tok) :eof)
          (error 'ad-incomplete-input
                 :message (format nil "expected ~a, got unexpected end of input" kind)
                 :start (token-start tok) :end (token-end tok))
          (error 'ad-parse-error
                 :message (format nil "expected ~a, got ~a `~a`" kind (token-kind tok) (token-text tok))
                 :start (token-start tok) :end (token-end tok))))
    (ts-consume! ts)))

;; Tokens that can start an atom, and so continue a juxtaposition (implicit-multiply) chain.
;; Deliberately excludes :minus -- "a - b" must parse as subtraction, not "a * (-b)".
(defparameter *atom-starters* '(:number :ident :backslash :lparen))

(defun parse-program (src)
  "Returns (values ast spans), spans an eq hash-table node -> span for eval-error
reporting (ticket 31); see *node-spans* above."
  (let* ((*node-spans* (make-hash-table :test 'eq))
         (tokens (tokenize src))
         (ts (make-token-stream tokens))
         (stmts (list (parse-statement! ts))))
    (loop while (eq (token-kind (ts-peek ts)) :semi) do
      (ts-consume! ts)
      (when (eq (token-kind (ts-peek ts)) :eof) (return))
      (push (parse-statement! ts) stmts))
    (setf stmts (nreverse stmts))
    (let ((tok (ts-peek ts)))
      (unless (eq (token-kind tok) :eof)
        (error 'ad-parse-error
               :message (format nil "unexpected token `~a`" (token-text tok))
               :start (token-start tok) :end (token-end tok))))
    (values (if (= (length stmts) 1) (first stmts) (make-seq stmts)) *node-spans*)))

(defun parse-statement! (ts)
  (let ((start (token-start (ts-peek ts))))
    (if (and (eq (token-kind (ts-peek ts)) :ident)
             (member (token-kind (ts-peek ts 1)) '(:eq :coloneq)))
        (let* ((name-tok (ts-consume! ts))
               (op-tok (ts-consume! ts))
               (value (parse-expr! ts)))
          (register-span! (make-assign (char (token-text name-tok) 0)
                                        (eq (token-kind op-tok) :coloneq) value)
                           start (ts-prev-end ts)))
        (parse-expr! ts))))

(defun parse-expr! (ts) (parse-additive! ts))

(defun parse-additive! (ts)
  (let ((start (token-start (ts-peek ts)))
        (node (parse-multiplicative! ts)))
    (loop while (member (token-kind (ts-peek ts)) '(:plus :minus)) do
      (let* ((op (if (eq (token-kind (ts-consume! ts)) :plus) :+ :-))
             (rhs (parse-multiplicative! ts)))
        (setf node (register-span! (make-bin-op op node rhs) start (ts-prev-end ts)))))
    node))

(defun parse-multiplicative! (ts)
  (let ((start (token-start (ts-peek ts)))
        (node (parse-juxtaposed! ts)))
    (loop while (member (token-kind (ts-peek ts)) '(:star :slash)) do
      (let* ((op (if (eq (token-kind (ts-consume! ts)) :star) :* :/))
             (rhs (parse-juxtaposed! ts)))
        (setf node (register-span! (make-bin-op op node rhs) start (ts-prev-end ts)))))
    node))

(defun parse-juxtaposed! (ts)
  (let ((start (token-start (ts-peek ts)))
        (node (parse-unary! ts)))
    (loop while (member (token-kind (ts-peek ts)) *atom-starters*) do
      (let ((rhs (parse-unary! ts)))
        (setf node (register-span! (make-bin-op :* node rhs) start (ts-prev-end ts)))))
    node))

(defun parse-unary! (ts)
  (if (eq (token-kind (ts-peek ts)) :minus)
      (let ((start (token-start (ts-consume! ts))))
        (register-span! (make-un-op :- (parse-unary! ts)) start (ts-prev-end ts)))
      (parse-power! ts)))

(defun parse-power! (ts)
  (let ((start (token-start (ts-peek ts)))
        (base (parse-atom! ts)))
    (if (eq (token-kind (ts-peek ts)) :caret)
        (progn (ts-consume! ts)
               (register-span! (make-bin-op :^ base (parse-unary! ts)) ; right-assoc; allows 2^-1, 2^3^2
                                start (ts-prev-end ts)))
        base)))

(defun parse-atom! (ts)
  (let ((tok (ts-peek ts)))
    (case (token-kind tok)
      (:number (ts-consume! ts) (register-span! (make-num-lit (token-text tok))
                                                  (token-start tok) (token-end tok)))
      (:ident (ts-consume! ts) (register-span! (make-var (char (token-text tok) 0))
                                                (token-start tok) (token-end tok)))
      (:backslash (ts-consume! ts) (register-span! (make-backslash-ref (token-text tok))
                                                    (token-start tok) (token-end tok)))
      (:lparen (ts-consume! ts)
               (let ((inner (parse-expr! ts)))
                 (ts-expect! ts :rparen)
                 inner))
      (t (if (eq (token-kind tok) :eof)
             (error 'ad-incomplete-input
                    :message "unexpected end of input"
                    :start (token-start tok) :end (token-end tok))
             (error 'ad-parse-error
                    :message (format nil "unexpected token `~a`" (token-text tok))
                    :start (token-start tok) :end (token-end tok)))))))

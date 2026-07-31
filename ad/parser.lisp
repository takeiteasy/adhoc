;;;; parser.lisp
;;;;
;;;; Precedence-climbing parser for phase-0 `ad`, over the grammar in docs/grammar.md.

(in-package #:adhoc/ad)

(defstruct (token-stream (:constructor make-token-stream (tokens &optional (pos 0))))
  tokens pos)

(defun ts-peek (ts &optional (offset 0))
  (let ((tokens (token-stream-tokens ts)))
    (nth (min (+ (token-stream-pos ts) offset) (1- (length tokens))) tokens)))

(defun ts-consume! (ts)
  (let ((tok (ts-peek ts)))
    (incf (token-stream-pos ts))
    tok))

(defun ts-expect! (ts kind)
  (let ((tok (ts-peek ts)))
    (unless (eq (token-kind tok) kind)
      (error 'ad-parse-error
             :message (format nil "expected ~a, got ~a `~a`" kind (token-kind tok) (token-text tok))
             :start (token-start tok) :end (token-end tok)))
    (ts-consume! ts)))

;; Tokens that can start an atom, and so continue a juxtaposition (implicit-multiply) chain.
;; Deliberately excludes :minus -- "a - b" must parse as subtraction, not "a * (-b)".
(defparameter *atom-starters* '(:number :ident :backslash :lparen))

(defun parse-program (src)
  (let* ((tokens (tokenize src))
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
    (if (= (length stmts) 1) (first stmts) (make-seq stmts))))

(defun parse-statement! (ts)
  (if (and (eq (token-kind (ts-peek ts)) :ident)
           (member (token-kind (ts-peek ts 1)) '(:eq :coloneq)))
      (let* ((name-tok (ts-consume! ts))
             (op-tok (ts-consume! ts))
             (value (parse-expr! ts)))
        (make-assign (char (token-text name-tok) 0) (eq (token-kind op-tok) :coloneq) value))
      (parse-expr! ts)))

(defun parse-expr! (ts) (parse-additive! ts))

(defun parse-additive! (ts)
  (let ((node (parse-multiplicative! ts)))
    (loop while (member (token-kind (ts-peek ts)) '(:plus :minus)) do
      (let* ((op (if (eq (token-kind (ts-consume! ts)) :plus) :+ :-))
             (rhs (parse-multiplicative! ts)))
        (setf node (make-bin-op op node rhs))))
    node))

(defun parse-multiplicative! (ts)
  (let ((node (parse-juxtaposed! ts)))
    (loop while (member (token-kind (ts-peek ts)) '(:star :slash)) do
      (let* ((op (if (eq (token-kind (ts-consume! ts)) :star) :* :/))
             (rhs (parse-juxtaposed! ts)))
        (setf node (make-bin-op op node rhs))))
    node))

(defun parse-juxtaposed! (ts)
  (let ((node (parse-unary! ts)))
    (loop while (member (token-kind (ts-peek ts)) *atom-starters*) do
      (let ((rhs (parse-unary! ts)))
        (setf node (make-bin-op :* node rhs))))
    node))

(defun parse-unary! (ts)
  (if (eq (token-kind (ts-peek ts)) :minus)
      (progn (ts-consume! ts) (make-un-op :- (parse-unary! ts)))
      (parse-power! ts)))

(defun parse-power! (ts)
  (let ((base (parse-atom! ts)))
    (if (eq (token-kind (ts-peek ts)) :caret)
        (progn (ts-consume! ts)
               (make-bin-op :^ base (parse-unary! ts))) ; right-assoc; allows 2^-1, 2^3^2
        base)))

(defun parse-atom! (ts)
  (let ((tok (ts-peek ts)))
    (case (token-kind tok)
      (:number (ts-consume! ts) (make-num-lit (token-text tok)))
      (:ident (ts-consume! ts) (make-var (char (token-text tok) 0)))
      (:backslash (ts-consume! ts) (make-backslash-ref (token-text tok)))
      (:lparen (ts-consume! ts)
               (let ((inner (parse-expr! ts)))
                 (ts-expect! ts :rparen)
                 inner))
      (t (error 'ad-parse-error
                :message (format nil "unexpected token `~a`" (token-text tok))
                :start (token-start tok) :end (token-end tok))))))

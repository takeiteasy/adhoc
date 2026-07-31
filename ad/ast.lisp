;;;; ast.lisp
;;;;
;;;; AST for phase-0 `ad`, as s-expression lists rather than typed structs -- the AST is
;;;; ordinary data a later phase's `\expr`/`\eval`/`\body` can quote, walk, and rewrite with
;;;; plain list operations. Node shape:
;;;;
;;;;   (:num-lit text)                  -- raw literal text; parsed to a Num value at eval
;;;;   (:var char)
;;;;   (:backslash-ref name)            -- name after `\`, e.g. "pi"; see below
;;;;   (:bin-op op lhs rhs)             -- op is :+ :- :* :/ :^
;;;;   (:un-op op operand)              -- op is :-
;;;;   (:assign char force value)       -- force distinguishes `:=` (t) from `=` (nil)
;;;;   (:seq statements)
;;;;
;;;; Deliberately small -- later phases add node tags; phase 4 compiles these to an
;;;; interaction net rather than changing this shape. See docs/architecture.md.
;;;;
;;;; `\`-name references: phase 0 seeds the lexer's name table but binds none of them, so
;;;; evaluating a :backslash-ref always raises an unbound-name error -- see docs/language.md.

(in-package #:adhoc/ad)

(declaim (inline node-tag))
(defun node-tag (node) (first node))

(defun make-num-lit (text) (list :num-lit text))
(defun num-lit-text (node) (second node))

(defun make-var (name) (list :var name))
(defun var-name (node) (second node))

(defun make-backslash-ref (name) (list :backslash-ref name))
(defun backslash-ref-name (node) (second node))

(defun make-bin-op (op lhs rhs) (list :bin-op op lhs rhs))
(defun bin-op-op (node) (second node))
(defun bin-op-lhs (node) (third node))
(defun bin-op-rhs (node) (fourth node))

(defun make-un-op (op operand) (list :un-op op operand))
(defun un-op-op (node) (second node))
(defun un-op-operand (node) (third node))

(defun make-assign (name force value) (list :assign name force value))
(defun assign-name (node) (second node))
(defun assign-force (node) (third node))
(defun assign-value (node) (fourth node))

(defun make-seq (statements) (list :seq statements))
(defun seq-statements (node) (second node))

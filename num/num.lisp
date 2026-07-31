;;;; num.lisp
;;;;
;;;; The numeric seam. src/interpreter never calls +/-/*/... directly on a value that came
;;;; from user input -- only through the functions here. See docs/numerics.md.
;;;;
;;;; Backing is CL's native tower: integer, ratio, double-float. CL ratios are already
;;;; canonical (a denominator of 1 is impossible), so unlike a hosted-in-a-language-without-
;;;; native-rationals implementation, there is no separate normalize step -- the tower's
;;;; "collapse to the lowest exact tier" rule is native, not implemented here. Later phases
;;;; (symbolic closed forms, algebraic numbers, RRA) add cases to these functions without
;;;; touching anything above this file.

(in-package #:adhoc/num)

;; The seam's own condition, distinct from a bare CL error, so callers (the interpreter's
;; :bin-op arm) can catch exactly "arithmetic went wrong" and re-signal it with a source
;; span, without also catching unrelated errors from evaluating the operands.
(define-condition ad-num-error (error)
  ((message :initarg :message :reader ad-num-error-message))
  (:report (lambda (c stream) (format stream "~a" (ad-num-error-message c)))))

(defun %to-double (x)
  (coerce x 'double-float))

(defun nadd (a b) (+ a b))
(defun nsub (a b) (- a b))
(defun nmul (a b) (* a b))

(defun ndiv (a b)
  (when (zerop b) (error 'ad-num-error :message "division by zero"))
  (if (or (floatp a) (floatp b))
      (/ (%to-double a) (%to-double b))
      (/ a b)))

(defun npow (a b)
  "Integer exponents stay exact (CL's EXPT handles negative exponents on rationals
natively, producing a rational rather than needing an invert-then-raise step). Any other
exponent falls to double-float."
  (cond
    ((and (zerop a) (integerp b) (minusp b))
     (error 'ad-num-error :message "division by zero"))
    ((integerp b) (expt a b))
    (t (expt (%to-double a) (%to-double b)))))

(defun nneg (a) (- a))

(defun neq (a b)
  "Equality for the assignment `x = e` re-check. Exact for integer/ratio, approximate float compare."
  (if (or (floatp a) (floatp b))
      (= (%to-double a) (%to-double b))
      (= a b)))

(defun nshow (a)
  "Display form. Exact rationals print as `a/b`; a ratio can never have denominator 1, so
this only ever fires for a genuinely non-integer exact value. Doubles print without CL's
`d0` exponent marker -- see docs/numerics.md on *read-default-float-format*."
  (etypecase a
    (integer (princ-to-string a))
    (ratio (format nil "~a/~a" (numerator a) (denominator a)))
    (double-float
     (let ((*read-default-float-format* 'double-float))
       (princ-to-string a)))))

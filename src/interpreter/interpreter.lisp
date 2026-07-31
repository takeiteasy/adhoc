;;;; interpreter.lisp
;;;;
;;;; Tree-walking evaluator for phase-0 `ad`. Disposable: phase 4 replaces this with an
;;;; interaction-net engine (see docs/architecture.md). All arithmetic goes through
;;;; adhoc/num.

(in-package #:adhoc/interpreter)

(define-condition ad-eval-error (error)
  ((message :initarg :message :reader ad-eval-error-message))
  (:report (lambda (c stream) (format stream "ERROR! ~a" (ad-eval-error-message c)))))

(defun make-env () (make-hash-table :test 'eql))

(defstruct (bind-result (:constructor make-bind-result (name value))) name value)
(defstruct (check-result (:constructor make-check-result (matches))) matches)
(defstruct (bare-result (:constructor make-bare-result (value))) value)

(defun %parse-literal (text)
  "Text is the raw literal as lexed. Integers are read directly (CL integers are already
arbitrary-precision); anything with a `.` is a double-float, read under a locally-bound
*read-default-float-format* so it doesn't depend on the reader's ambient default."
  (if (find #\. text)
      (let ((*read-default-float-format* 'double-float))
        (coerce (read-from-string text) 'double-float))
      (parse-integer text)))

(defun eval-expr (env node)
  (ecase (adhoc/ad:node-tag node)
    (:num-lit (%parse-literal (adhoc/ad:num-lit-text node)))
    (:var (let ((name (adhoc/ad:var-name node)))
            (multiple-value-bind (value present) (gethash name env)
              (unless present
                (error 'ad-eval-error :message (format nil "`~a` does not exist!" name)))
              value)))
    (:backslash-ref
     (error 'ad-eval-error
            :message (format nil "`\\~a` is not bound (phase 0 defines no builtins yet)"
                              (adhoc/ad:backslash-ref-name node))))
    (:un-op (adhoc/num:nneg (eval-expr env (adhoc/ad:un-op-operand node))))
    (:bin-op
     (let ((lhs (eval-expr env (adhoc/ad:bin-op-lhs node)))
           (rhs (eval-expr env (adhoc/ad:bin-op-rhs node))))
       (ecase (adhoc/ad:bin-op-op node)
         (:+ (adhoc/num:nadd lhs rhs))
         (:- (adhoc/num:nsub lhs rhs))
         (:* (adhoc/num:nmul lhs rhs))
         (:/ (adhoc/num:ndiv lhs rhs))
         (:^ (adhoc/num:npow lhs rhs)))))))

(defun run! (env node)
  (case (adhoc/ad:node-tag node)
    (:assign
     (let ((name (adhoc/ad:assign-name node))
           (value (eval-expr env (adhoc/ad:assign-value node))))
       (multiple-value-bind (existing present) (gethash name env)
         (cond
           ((adhoc/ad:assign-force node)
            (unless present
              (error 'ad-eval-error :message (format nil "`~a` does not exist!" name)))
            (setf (gethash name env) value)
            (make-bind-result name value))
           (present (make-check-result (adhoc/num:neq existing value)))
           (t (setf (gethash name env) value)
              (make-bind-result name value))))))
    (:seq
     (let ((result nil))
       (dolist (stmt (adhoc/ad:seq-statements node))
         (setf result (run! env stmt)))
       (unless result
         (error 'ad-eval-error :message "empty statement sequence"))
       result))
    (t (make-bare-result (eval-expr env node)))))

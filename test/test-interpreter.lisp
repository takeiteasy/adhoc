;;;; test-interpreter.lisp
;;;;
;;;; AST-level tests, no parser involved -- mirrors what test-parser.lisp exercises through
;;;; source text.

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(test interpreter-literals-and-arithmetic
  (let ((env (adhoc/interpreter:make-env))
        (node (adhoc/ad:make-bin-op :+ (adhoc/ad:make-num-lit "1")
                                     (adhoc/ad:make-bin-op :* (adhoc/ad:make-num-lit "2")
                                                            (adhoc/ad:make-num-lit "3")))))
    (is (= (adhoc/interpreter:eval-expr env node) 7))))

(test interpreter-unbound-variable-reference-errors-with-expected-message
  (let ((env (adhoc/interpreter:make-env)))
    (handler-case
        (progn (adhoc/interpreter:eval-expr env (adhoc/ad:make-var #\q))
               (fail "expected ad-eval-error"))
      (adhoc/interpreter:ad-eval-error (e)
        (is (search "`q` does not exist!" (adhoc/interpreter:ad-eval-error-message e)))))))

(test interpreter-force-reassign-of-an-unbound-name-errors
  (let ((env (adhoc/interpreter:make-env))
        (node (adhoc/ad:make-assign #\y t (adhoc/ad:make-num-lit "5"))))
    (signals adhoc/interpreter:ad-eval-error (adhoc/interpreter:run! env node))))

(test interpreter-eq-binds-when-unbound-checks-when-bound
  (let ((env (adhoc/interpreter:make-env)))
    (let ((r1 (adhoc/interpreter:run! env (adhoc/ad:make-assign #\x nil (adhoc/ad:make-num-lit "3")))))
      (is-true (adhoc/interpreter:bind-result-p r1))
      (is (= (adhoc/interpreter:bind-result-value r1) 3)))
    (let ((r2 (adhoc/interpreter:run! env (adhoc/ad:make-assign #\x nil (adhoc/ad:make-num-lit "3")))))
      (is-true (adhoc/interpreter:check-result-p r2))
      (is-true (adhoc/interpreter:check-result-matches r2)))
    (let ((r3 (adhoc/interpreter:run! env (adhoc/ad:make-assign #\x nil (adhoc/ad:make-num-lit "4")))))
      (is-true (adhoc/interpreter:check-result-p r3))
      (is-false (adhoc/interpreter:check-result-matches r3)))))

(test interpreter-coloneq-rebinds-when-bound
  (let ((env (adhoc/interpreter:make-env)))
    (setf (gethash #\x env) 3)
    (let ((r (adhoc/interpreter:run! env (adhoc/ad:make-assign #\x t (adhoc/ad:make-num-lit "4")))))
      (is-true (adhoc/interpreter:bind-result-p r))
      (is (= (gethash #\x env) 4)))))

(test interpreter-seq-threads-env-and-returns-the-last-result
  (let* ((env (adhoc/interpreter:make-env))
         (node (adhoc/ad:make-seq
                (list (adhoc/ad:make-assign #\a nil (adhoc/ad:make-num-lit "2"))
                      (adhoc/ad:make-assign #\b nil (adhoc/ad:make-num-lit "3"))
                      (adhoc/ad:make-bin-op :* (adhoc/ad:make-var #\a) (adhoc/ad:make-var #\b)))))
         (r (adhoc/interpreter:run! env node)))
    (is-true (adhoc/interpreter:bare-result-p r))
    (is (= (adhoc/interpreter:bare-result-value r) 6))
    (is (and (= (gethash #\a env) 2) (= (gethash #\b env) 3)))))

(test interpreter-referencing-a-backslash-name-errors-unbound-in-phase-0
  (let ((env (adhoc/interpreter:make-env)))
    (signals adhoc/interpreter:ad-eval-error
      (adhoc/interpreter:eval-expr env (adhoc/ad:make-backslash-ref "pi")))))

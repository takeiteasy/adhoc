;;;; test-grammar.lisp
;;;;
;;;; Parity checks lifted directly from docs/grammar.md's worked examples and assignment-
;;;; semantics table, plus the float-format and unicode cases those docs don't cover but a
;;;; dumped-image launch is exposed to. See docs/numerics.md and src/cli/cli.lisp.

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(defun %parse-eval (env src)
  (adhoc/interpreter:run! env (adhoc/ad:parse-program src)))

(defun %value-of (result)
  (cond
    ((adhoc/interpreter:bind-result-p result) (adhoc/interpreter:bind-result-value result))
    ((adhoc/interpreter:check-result-p result) (adhoc/interpreter:check-result-matches result))
    ((adhoc/interpreter:bare-result-p result) (adhoc/interpreter:bare-result-value result))))

(test grammar-worked-examples
  (let ((*read-default-float-format* 'double-float))
    (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "1 + 2 * 3")) 7))
    (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "(1 + 2) * 3")) 9))
    (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "-2^2")) -4))
    (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "2^-1")) 1/2))
    (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "2^3^2")) 512))
    (let ((env (adhoc/interpreter:make-env)))
      (setf (gethash #\x env) 4)
      (is (= (%value-of (%parse-eval env "1/2x")) 1/8)))
    (let ((env (adhoc/interpreter:make-env)))
      (setf (gethash #\x env) 4)
      (is (= (%value-of (%parse-eval env "2x^2")) 32)))))

(test grammar-assignment-semantics-table
  (let ((env (adhoc/interpreter:make-env)))
    ;; x = e, x unbound -> bind
    (let ((r (%parse-eval env "x = 1")))
      (is-true (adhoc/interpreter:bind-result-p r))
      (is (= (adhoc/interpreter:bind-result-value r) 1)))
    ;; x = e, x bound, mismatched -> compare, false
    (is-false (adhoc/interpreter:check-result-matches (%parse-eval env "x = 2")))
    ;; x = e, x bound, matching -> compare, true
    (is-true (adhoc/interpreter:check-result-matches (%parse-eval env "x = 1")))
    ;; x := e, x bound -> rebind
    (let ((r (%parse-eval env "x := 2")))
      (is-true (adhoc/interpreter:bind-result-p r))
      (is (= (adhoc/interpreter:bind-result-value r) 2)))
    ;; x := e, x unbound -> error
    (signals adhoc/interpreter:ad-eval-error (%parse-eval env "y := 5"))))

(test grammar-exactness
  (is (= (%value-of (%parse-eval (adhoc/interpreter:make-env) "1/3 + 1/3 + 1/3")) 1))
  (is (string= (adhoc/num:nshow (%value-of (%parse-eval (adhoc/interpreter:make-env) "1/2"))) "1/2")))

(test grammar-float-parity
  "Guards against *read-default-float-format*'s single-float default: a literal read as
text must come back a double, and a double must print without CL's `d0` marker."
  (let ((r (%value-of (%parse-eval (adhoc/interpreter:make-env) "0.5 + 0.5"))))
    (is (typep r 'double-float))
    (is (string= (adhoc/num:nshow r) "1.0")))
  (let ((r (%value-of (%parse-eval (adhoc/interpreter:make-env) "2^0.5"))))
    (is (typep r 'double-float))
    (is (string= (adhoc/num:nshow r) "1.4142135623730951"))))

(test grammar-unicode-identifier
  (let* ((env (adhoc/interpreter:make-env))
         (r (%parse-eval env "π = 3")))
    (is-true (adhoc/interpreter:bind-result-p r))
    (is (= (gethash #\π env) 3))))

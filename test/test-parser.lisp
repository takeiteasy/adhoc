;;;; test-parser.lisp

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(defun %ev (env src)
  "Parse + evaluate a single line in ENV, returning the underlying value regardless of
result kind."
  (let ((r (adhoc/interpreter:run! env (adhoc/ad:parse-program src))))
    (cond
      ((adhoc/interpreter:bind-result-p r) (adhoc/interpreter:bind-result-value r))
      ((adhoc/interpreter:check-result-p r) (adhoc/interpreter:check-result-matches r))
      ((adhoc/interpreter:bare-result-p r) (adhoc/interpreter:bare-result-value r))
      (t (error "unreachable")))))

(defun %ev1 (src) (%ev (adhoc/interpreter:make-env) src))

(test parser-eval-precedence
  (is (= (%ev1 "1 + 2 * 3") 7))
  (is (= (%ev1 "(1 + 2) * 3") 9))
  (is (= (%ev1 "-2^2") -4))
  (is (= (%ev1 "2^-1") 1/2))
  (is (= (%ev1 "2^3^2") 512))
  (let ((env (adhoc/interpreter:make-env)))
    (setf (gethash #\x env) 4)
    (is (= (%ev env "1/2x") 1/8)))    ; 1/(2x), not (1/2)x
  (let ((env (adhoc/interpreter:make-env)))
    (setf (gethash #\x env) 4)
    (is (= (%ev env "2x^2") 32))))    ; 2*(x^2), not (2x)^2

(test parser-eval-assignment-semantics
  (let ((env (adhoc/interpreter:make-env)))
    (is (= (%ev env "x = 1 + 2") 3))
    (is (= (gethash #\x env) 3))

    (is-false (%ev env "x = 4")) ; bound + mismatched value -> compare, false
    (is-true (%ev env "x = 3"))  ; bound + matching value -> compare, true

    (is (= (%ev env "x := 4") 4))
    (is (= (gethash #\x env) 4))

    (signals adhoc/interpreter:ad-eval-error (%ev env "y := 5"))))

(test parser-eval-grammar-worked-examples
  (is (= (%ev1 "1 + 2 * 3") 7))
  (is (= (%ev1 "(1 + 2) * 3") 9))
  (let ((env (adhoc/interpreter:make-env)))
    (is (= (%ev env "x = 1 + 2") 3))
    (is-false (%ev env "x = 4"))
    (is (= (%ev env "x := 4") 4))
    (signals adhoc/interpreter:ad-eval-error (%ev env "y := 5")))
  (is (= (%ev1 "1/3 + 1/3 + 1/3") 1)))

(test backslash-names-lex-and-reference-but-are-unbound-in-phase-0
  (let ((ast (adhoc/ad:parse-program "\\pi")))
    (is (eq (adhoc/ad:node-tag ast) :backslash-ref)))
  (signals adhoc/interpreter:ad-eval-error (%ev1 "\\pi"))
  (signals adhoc/ad:ad-lex-error (adhoc/ad:parse-program "\\pih")))

(test parse-errors
  (signals adhoc/ad:ad-parse-error (adhoc/ad:parse-program "1 +"))
  (signals adhoc/ad:ad-parse-error (adhoc/ad:parse-program "(1 + 2")))

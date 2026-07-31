;;;; test-diagnostics.lisp
;;;;
;;;; Source spans (ticket 7) and the caret-pointing renderer they feed.

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(defun %tok-span (src index)
  (let ((tok (nth index (adhoc/ad:tokenize src))))
    (list (adhoc/ad:token-start tok) (adhoc/ad:token-end tok))))

(test token-spans
  (is (equal (%tok-span "3 12.34" 0) '(0 1)))
  (is (equal (%tok-span "3 12.34" 1) '(2 7)))
  (is (equal (%tok-span "ab" 0) '(0 1)))
  (is (equal (%tok-span "ab" 1) '(1 2)))
  ;; a `\`-token's span covers the sigil, since that's what the caret underlines.
  (is (equal (%tok-span "\\pi" 0) '(0 3)))
  (let ((toks (adhoc/ad:tokenize "x")))
    (is (equal (list (adhoc/ad:token-start (car (last toks)))
                      (adhoc/ad:token-end (car (last toks))))
               '(1 1))))) ; :eof is zero-width at the end of the source

(test lex-error-spans
  (handler-case (adhoc/ad:tokenize "1 & 2")
    (adhoc/ad:ad-lex-error (e)
      (is (= (adhoc/ad:ad-error-start e) 2))
      (is (= (adhoc/ad:ad-error-end e) 3))))
  (handler-case (adhoc/ad:tokenize "\\notaname")
    (adhoc/ad:ad-lex-error (e)
      (is (= (adhoc/ad:ad-error-start e) 0))
      (is (= (adhoc/ad:ad-error-end e) 9)))))

(test parse-error-spans
  (handler-case (adhoc/ad:parse-program "1 + * 2")
    (adhoc/ad:ad-parse-error (e)
      (is (= (adhoc/ad:ad-error-start e) 4))
      (is (= (adhoc/ad:ad-error-end e) 5))))
  (handler-case (adhoc/ad:parse-program "(1 + 2")
    (adhoc/ad:ad-parse-error (e)
      ;; ran out of input looking for `)` -- the error points at the zero-width :eof span.
      (is (= (adhoc/ad:ad-error-start e) 6))
      (is (= (adhoc/ad:ad-error-end e) 6)))))

(test render-diagnostic-golden-string
  (is (string= (with-output-to-string (s)
                 (adhoc/ad:render-diagnostic s "1 + * 2" "ERROR!" "unexpected token `*`" 4 5))
               (format nil "< ERROR! unexpected token `*`~%    1 + * 2~%        ^~%"))))

(test eval-error-spans-narrow-to-the-failing-sub-expression
  ;; The discriminating cases: if the span table isn't being consulted, these underline the
  ;; whole line instead of just the offending piece.
  (flet ((%eval-span (src)
           (multiple-value-bind (ast spans) (adhoc/ad:parse-program src)
             (handler-case (progn (adhoc/interpreter:run! (adhoc/interpreter:make-env) ast spans)
                                   (fail "expected ad-eval-error"))
               (adhoc/interpreter:ad-eval-error (e)
                 (list (adhoc/interpreter:ad-eval-error-start e)
                       (adhoc/interpreter:ad-eval-error-end e)))))))
    (is (equal (%eval-span "1 + x") '(4 5)))            ; only `x`, not the whole line
    (is (equal (%eval-span "2 + 1/0") '(4 7)))           ; only `1/0`
    (is (equal (%eval-span "\\pi") '(0 3)))              ; the sigil-inclusive `\`-token
    (is (equal (%eval-span "a=1; y:=2") '(5 9)))))       ; only the second statement

(test incomplete-input-is-a-distinct-parse-error-subclass
  (dolist (src '("(1 + 2" "1 +" "2 ^" "x ="))
    (signals adhoc/ad:ad-incomplete-input (adhoc/ad:parse-program src)))
  ;; a genuine parse error (not just running out of input) stays a plain ad-parse-error
  (handler-case (progn (adhoc/ad:parse-program "1 + * 2") (fail "expected ad-parse-error"))
    (adhoc/ad:ad-incomplete-input () (fail "should not be incomplete-input"))
    (adhoc/ad:ad-parse-error () nil)))

(test repl-continuation-prompt-accepts-a-multi-line-statement
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "(1 +~%2)~%")) out)
    (is (search "< = 3" (get-output-stream-string out)))))

(test repl-blank-line-cancels-a-pending-continuation
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "(1 +~%~%1+1~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "cancelled" text))
      (is (search "< = 2" text))))) ; the loop recovered and evaluated the next line

(test repl-read-line-fn-receives-the-current-prompt
  ;; Pins the contract cli/lineedit.lisp relies on: run-repl calls its custom reader as
  ;; (funcall read-line-fn stream prompt), where prompt is "> " for a fresh statement and
  ;; ". " for a continuation -- cl-readline needs that text for :already-prompted redisplay.
  (let* ((out (make-string-output-stream))
         (lines (list "(1 +" "2)"))
         (prompts nil)
         (reader (lambda (stream prompt)
                   (declare (ignore stream))
                   (push prompt prompts)
                   (or (pop lines) :eof))))
    (adhoc/repl:run-repl *standard-input* out reader)
    ;; "> " for the first line, ". " for the continuation, then a fresh "> " for the next
    ;; statement (which immediately hits :eof and ends the session).
    (is (equal (reverse prompts) '("> " ". " "> ")))
    (is (search "< = 3" (get-output-stream-string out)))))

(test repl-explicit-semicolon-terminates-a-statement-immediately
  ;; `1;` and `2;` are already-complete statements (a trailing `;` with nothing after just
  ;; ends parse-program's loop) -- they must not trigger a continuation prompt.
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "1;~%2;~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "< = 1" text))
      (is (search "< = 2" text))
      (is (not (search ". " text))))))

(test repl-end-of-stream-mid-statement-reports-the-pending-error
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "(1 +~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "ERROR!" text))
      (is (search "^" text)))))

(test num-division-by-zero-is-a-typed-condition
  (signals adhoc/num:ad-num-error (adhoc/num:ndiv 1 0))
  (signals adhoc/num:ad-num-error (adhoc/num:npow 0 -1)))

(test repl-renders-caret-and-keeps-going
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "1 + * 2~%1 + 1~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "unexpected token `*`" text))
      (is (search "^" text))
      (is (search "< = 2" text))))) ; the loop recovered and evaluated the next line

(test repl-division-by-zero-is-recovered-not-a-crash
  ;; Regression for a bug found while working ticket 31: ndiv signalling a bare CL error
  ;; wasn't caught by run-repl's handler-case, and cli.lisp's debugger-hook backstop never
  ;; installed (interned into the wrong package), so `1/0` crashed the whole process.
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "1/0~%1+1~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "division by zero" text))
      (is (search "< = 2" text)))))

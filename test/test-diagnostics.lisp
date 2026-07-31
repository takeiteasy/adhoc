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

(test repl-renders-caret-and-keeps-going
  (let ((out (make-string-output-stream)))
    (adhoc/repl:run-repl (make-string-input-stream (format nil "1 + * 2~%1 + 1~%")) out)
    (let ((text (get-output-stream-string out)))
      (is (search "unexpected token `*`" text))
      (is (search "^" text))
      (is (search "< = 2" text))))) ; the loop recovered and evaluated the next line

;;;; repl.lisp
;;;;
;;;; REPL glue for phase-0 `ad`: `> ` prompt, `< `-prefixed output, per-line error recovery,
;;;; clean exit on EOF. Disposable, same as src/interpreter -- see docs/architecture.md.

(in-package #:adhoc/repl)

(defun %format-result (result)
  (cond
    ((adhoc/interpreter:bind-result-p result)
     (format nil "~a = ~a" (adhoc/interpreter:bind-result-name result)
             (adhoc/num:nshow (adhoc/interpreter:bind-result-value result))))
    ((adhoc/interpreter:check-result-p result)
     (if (adhoc/interpreter:check-result-matches result) "true" "false"))
    ((adhoc/interpreter:bare-result-p result)
     (format nil "= ~a" (adhoc/num:nshow (adhoc/interpreter:bare-result-value result))))))

(defun run-repl (&optional (in *standard-input*) (out *standard-output*))
  (let ((env (adhoc/interpreter:make-env)))
    (loop
      (format out "> ")
      (force-output out)
      (let ((line (read-line in nil :eof)))
        (when (eq line :eof) (return))
        (unless (zerop (length (string-trim '(#\Space #\Tab #\Return) line)))
          (handler-case
              (let ((tokens (adhoc/ad:tokenize line)))
                (unless (= (length tokens) 1) ; blank or comment-only line: nothing to do
                  (let* ((ast (adhoc/ad:parse-program line))
                         (result (adhoc/interpreter:run! env ast)))
                    (format out "< ~a~%" (%format-result result)))))
            (adhoc/ad:ad-lex-error (e) (format out "< ERROR! ~a~%" (adhoc/ad:ad-error-message e)))
            (adhoc/ad:ad-parse-error (e) (format out "< ERROR! ~a~%" (adhoc/ad:ad-error-message e)))
            (adhoc/interpreter:ad-eval-error (e)
              (format out "< ERROR! ~a~%" (adhoc/interpreter:ad-eval-error-message e)))))))
    (format out "~%")))

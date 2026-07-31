;;;; repl.lisp
;;;;
;;;; REPL glue for phase-0 `ad`: `> ` prompt, `< `-prefixed output, per-statement error
;;;; recovery, clean exit on EOF, and `. ` continuation prompts for a statement that spans
;;;; more than one input line (ticket 32). Disposable, same as src/interpreter -- see
;;;; docs/architecture.md.

(in-package #:adhoc/repl)

(defun %render-error (out source e)
  (adhoc/ad:render-diagnostic out source "ERROR!" (adhoc/ad:ad-error-message e)
                               (adhoc/ad:ad-error-start e) (adhoc/ad:ad-error-end e)))

(defun %format-result (result)
  (cond
    ((adhoc/interpreter:bind-result-p result)
     (format nil "~a = ~a" (adhoc/interpreter:bind-result-name result)
             (adhoc/num:nshow (adhoc/interpreter:bind-result-value result))))
    ((adhoc/interpreter:check-result-p result)
     (if (adhoc/interpreter:check-result-matches result) "true" "false"))
    ((adhoc/interpreter:bare-result-p result)
     (format nil "= ~a" (adhoc/num:nshow (adhoc/interpreter:bare-result-value result))))))

(defun run-repl (&optional (in *standard-input*) (out *standard-output*) (read-line-fn nil))
  "READ-LINE-FN, if given, is called as (funcall read-line-fn in prompt) instead of
CL:READ-LINE to fetch the next line -- the hook cli/lineedit.lisp uses to route through
cl-readline instead of a plain stream read. PROMPT is the \"> \"/\". \" string this call
already printed to OUT, passed through so a reader like cl-readline's can tell its redisplay
logic what's on the line already, via :already-prompted, instead of printing it again.
Defaults to (read-line in nil :eof), which ignores prompt."
  (let ((env (adhoc/interpreter:make-env))
        (buffer nil) ; NIL when no statement is pending; otherwise the accumulated source
        (%read-line (or read-line-fn (lambda (stream prompt) (declare (ignore prompt))
                                        (read-line stream nil :eof)))))
    (loop
      (let* ((prompt (if buffer ". " "> "))
             (line (progn (format out prompt) (force-output out)
                          (funcall %read-line in prompt))))
        (when (eq line :eof)
          (when buffer
            ;; End of stream mid-statement: report the pending error rather than exiting
            ;; silently -- a piped "(1 +\n" must still surface a diagnostic.
            (handler-case (adhoc/ad:parse-program buffer)
              (adhoc/ad:ad-lex-error (e) (%render-error out buffer e))
              (adhoc/ad:ad-parse-error (e) (%render-error out buffer e))))
          (return))
        (let ((blank (zerop (length (string-trim '(#\Space #\Tab #\Return) line)))))
          (cond
            ((and (not buffer) blank)) ; nothing pending, blank line: no-op
            ((and buffer blank)
             ;; A blank line cancels a pending multi-line statement -- ad's whitespace is
             ;; insignificant, so nothing else would ever close an unclosed continuation.
             (format out "-- input cancelled~%")
             (setf buffer nil))
            (t
             (let ((source (if buffer (concatenate 'string buffer (string #\Newline) line) line))
                   (still-pending nil))
               (handler-case
                   (let ((tokens (adhoc/ad:tokenize source)))
                     (unless (= (length tokens) 1) ; blank or comment-only line: nothing to do
                       (multiple-value-bind (ast spans) (adhoc/ad:parse-program source)
                         (let ((result (adhoc/interpreter:run! env ast spans)))
                           (format out "< ~a~%" (%format-result result))))))
                 ;; ad-incomplete-input is a subclass of ad-parse-error, so this clause must
                 ;; come first -- handler-case picks the first matching clause, and the
                 ;; parse-error clause below would otherwise shadow it.
                 (adhoc/ad:ad-incomplete-input () (setf still-pending t))
                 (adhoc/ad:ad-lex-error (e) (%render-error out source e))
                 (adhoc/ad:ad-parse-error (e) (%render-error out source e))
                 (adhoc/interpreter:ad-eval-error (e)
                   (adhoc/ad:render-diagnostic out source "ERROR!"
                                                (adhoc/interpreter:ad-eval-error-message e)
                                                (or (adhoc/interpreter:ad-eval-error-start e) 0)
                                                (or (adhoc/interpreter:ad-eval-error-end e)
                                                    (length source)))))
               (setf buffer (and still-pending source))))))))
    (format out "~%")))

;;;; cli.lisp
;;;;
;;;; adhoc entry point. Four things a dumped-image launch needs that an interactive REPL
;;;; session gets for free:
;;;;
;;;;   - *read-default-float-format* bound to double-float, so float literals read (and
;;;;     print, via adhoc/num:nshow) as doubles rather than CL's single-float default.
;;;;   - stdin/stdout reopened with an explicit UTF-8 external format, so unicode
;;;;     identifiers (`π`, ...) work independent of the ambient locale under `ros build`.
;;;;   - sb-ext:*invoke-debugger-hook* set, so an unhandled condition prints a message and
;;;;     exits instead of dropping into SBCL's low-level debugger (LDB) with no controlling
;;;;     terminal -- adhoc/repl already turns every ad-* condition into a `< ERROR! ...`
;;;;     line and keeps going; this hook is the backstop for anything it doesn't catch.
;;;;   - in-process readline (cli/lineedit.lisp) on an interactive tty, with a `--has-readline`
;;;;     probe bin/adhoc uses to decide whether it needs to fall back to wrapping in `rlwrap`.

(in-package #:adhoc/cli)

#+sbcl
(defun %reopen-stdio-utf8 ()
  (setf *standard-input*
        (sb-sys:make-fd-stream 0 :input t :external-format :utf-8 :buffering :line))
  (setf *standard-output*
        (sb-sys:make-fd-stream 1 :output t :external-format :utf-8 :buffering :line)))

#+sbcl
(defun %install-debugger-hook ()
  (setf sb-ext:*invoke-debugger-hook*
        (lambda (condition hook)
          (declare (ignore hook))
          (format *error-output* "Fatal error: ~a~%" condition)
          (finish-output *error-output*)
          (uiop:quit 1))))

(defun main (&optional args)
  (let ((*read-default-float-format* 'double-float))
    #+sbcl (%reopen-stdio-utf8)
    #+sbcl (%install-debugger-hook)
    (if (member "--has-readline" args :test #'string=)
        ;; bin/adhoc's handshake (docs/architecture.md): print whether this build can use
        ;; in-process readline for *this* invocation, so the launcher knows whether to fall
        ;; back to wrapping in rlwrap instead. Exits without starting the REPL.
        (progn (format t "~:[no~;yes~]~%" (readline-available-p))
               (finish-output)
               (uiop:quit 0))
        (if (readline-available-p)
            (unwind-protect
                 (adhoc/repl:run-repl *standard-input* *standard-output* #'readline-read-line)
              (save-history))
            (adhoc/repl:run-repl)))))

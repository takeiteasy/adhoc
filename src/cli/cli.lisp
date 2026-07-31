;;;; cli.lisp
;;;;
;;;; adhoc entry point. Three things a dumped-image launch needs that an interactive REPL
;;;; session gets for free:
;;;;
;;;;   - *read-default-float-format* bound to double-float, so float literals read (and
;;;;     print, via adhoc/num:nshow) as doubles rather than CL's single-float default.
;;;;   - stdin/stdout reopened with an explicit UTF-8 external format, so unicode
;;;;     identifiers (`π`, ...) work independent of the ambient locale under `ros build`.
;;;;   - *invoke-debugger-hook* set, so an unhandled condition prints a message and exits
;;;;     instead of dropping into SBCL's low-level debugger (LDB) with no controlling
;;;;     terminal -- adhoc/repl already turns every ad-* condition into a `< ERROR! ...`
;;;;     line and keeps going; this hook is the backstop for anything it doesn't catch.

(in-package #:adhoc/cli)

#+sbcl
(defun %reopen-stdio-utf8 ()
  (setf *standard-input*
        (sb-sys:make-fd-stream 0 :input t :external-format :utf-8 :buffering :line))
  (setf *standard-output*
        (sb-sys:make-fd-stream 1 :output t :external-format :utf-8 :buffering :line)))

(defun %install-debugger-hook ()
  (setf *invoke-debugger-hook*
        (lambda (condition hook)
          (declare (ignore hook))
          (format *error-output* "Fatal error: ~a~%" condition)
          (finish-output *error-output*)
          (uiop:quit 1))))

(defun main (&optional args)
  (declare (ignore args)) ; phase 0 has no script mode / CLI flags yet
  (let ((*read-default-float-format* 'double-float))
    #+sbcl (%reopen-stdio-utf8)
    (%install-debugger-hook)
    (adhoc/repl:run-repl)))

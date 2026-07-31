;;;; package.lisp -- adhoc/interpreter

(defpackage #:adhoc/interpreter
  (:use #:cl)
  (:export
   #:make-env
   #:ad-eval-error #:ad-eval-error-message
   #:run!
   #:eval-expr
   #:bind-result-p #:bind-result-name #:bind-result-value
   #:check-result-p #:check-result-matches
   #:bare-result-p #:bare-result-value))

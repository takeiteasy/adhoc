;;;; package.lisp -- adhoc/ad

(defpackage #:adhoc/ad
  (:use #:cl)
  (:export
   ;; conditions
   #:ad-lex-error #:ad-parse-error #:ad-error-message #:ad-error-pos
   ;; lexer
   #:tokenize #:token-kind #:token-text #:token-pos
   ;; ast constructors and accessors
   #:make-num-lit #:num-lit-text
   #:make-var #:var-name
   #:make-backslash-ref #:backslash-ref-name
   #:make-bin-op #:bin-op-op #:bin-op-lhs #:bin-op-rhs
   #:make-un-op #:un-op-op #:un-op-operand
   #:make-assign #:assign-name #:assign-force #:assign-value
   #:make-seq #:seq-statements
   #:node-tag
   ;; parser
   #:parse-program))

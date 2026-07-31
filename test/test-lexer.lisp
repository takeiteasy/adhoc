;;;; test-lexer.lisp

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(defun %tok-kinds (tokens) (mapcar #'adhoc/ad:token-kind tokens))

(test lexer-numbers
  (let ((toks (adhoc/ad:tokenize "3 12.34")))
    (is (eq (adhoc/ad:token-kind (first toks)) :number))
    (is (string= (adhoc/ad:token-text (first toks)) "3"))
    (is (eq (adhoc/ad:token-kind (second toks)) :number))
    (is (string= (adhoc/ad:token-text (second toks)) "12.34"))
    (is (eq (adhoc/ad:token-kind (car (last toks))) :eof))))

(test lexer-identifiers-ascii-and-unicode
  (let ((toks (adhoc/ad:tokenize "ab π")))
    (is (equal (%tok-kinds (subseq toks 0 3)) '(:ident :ident :ident)))
    (is (string= (adhoc/ad:token-text (first toks)) "a"))
    (is (string= (adhoc/ad:token-text (second toks)) "b"))
    (is (string= (adhoc/ad:token-text (third toks)) "π"))))

(test lexer-backslash-names
  (let* ((toks (adhoc/ad:tokenize "\\pi + \\sin(x)"))
         (kinds (%tok-kinds toks)))
    (is (eq (adhoc/ad:token-kind (first toks)) :backslash))
    (is (string= (adhoc/ad:token-text (first toks)) "pi"))
    (is (member :backslash kinds))
    (is (= (count :backslash kinds) 2))))

(test lexer-unknown-backslash-name-errors
  (signals adhoc/ad:ad-lex-error (adhoc/ad:tokenize "\\notaname")))

(test lexer-comments-are-discarded
  (is (equal (%tok-kinds (adhoc/ad:tokenize (format nil "1 -- comment~%+ 2")))
             '(:number :plus :number :eof))))

(test lexer-operators
  (let ((toks (adhoc/ad:tokenize "+ - * / ^ = := ( ) ;")))
    (is (equal (%tok-kinds (butlast toks))
               '(:plus :minus :star :slash :caret :eq :coloneq :lparen :rparen :semi)))))

(test lexer-unexpected-character-errors
  (signals adhoc/ad:ad-lex-error (adhoc/ad:tokenize "1 & 2")))

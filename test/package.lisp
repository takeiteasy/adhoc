;;;; package.lisp -- adhoc/tests

(defpackage #:adhoc/tests
  (:use #:cl #:fiveam)
  (:export #:adhoc-suite))

(in-package #:adhoc/tests)

(def-suite adhoc-suite)
(in-suite adhoc-suite)

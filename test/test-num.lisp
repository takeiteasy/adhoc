;;;; test-num.lisp

(in-package #:adhoc/tests)
(in-suite adhoc-suite)

(test num-exact-rational-arithmetic
  (let* ((third (adhoc/num:ndiv 1 3))
         (s (adhoc/num:nadd (adhoc/num:nadd third third) third)))
    (is (= s 1))
    (is (integerp s))))

(test num-integer-division-collapses-when-exact
  (is (eql (adhoc/num:ndiv 6 3) 2))
  (is (integerp (adhoc/num:ndiv 6 3)))
  (is (= (adhoc/num:ndiv 1 2) 1/2)))

(test num-npow-keeps-rationals-exact-for-integer-exponents
  (is (= (adhoc/num:npow 2 10) 1024))
  (is (= (adhoc/num:npow 1/2 2) 1/4))
  (is (= (adhoc/num:npow 2 -1) 1/2)))

(test num-division-by-zero-errors
  (signals error (adhoc/num:ndiv 1 0)))

(test num-neq
  (is-true (adhoc/num:neq 4 8/2))
  (is-false (adhoc/num:neq 4 5)))

(test num-display-exact-rationals-show-as-a/b-never-decimal
  (is (string= (adhoc/num:nshow (adhoc/num:ndiv 1 2)) "1/2"))
  (is (string= (adhoc/num:nshow (adhoc/num:ndiv 1 3)) "1/3"))
  (is (string= (adhoc/num:nshow (adhoc/num:ndiv 4 2)) "2")) ; collapses to an integer first
  (is (string= (adhoc/num:nshow 7) "7")))

(test num-float-parity
  "*read-default-float-format* traps: doubles must print without CL's `d0` marker, and
0.5 read as text must come back a double, not a single-float."
  (is (string= (adhoc/num:nshow (adhoc/num:nadd 0.5d0 0.5d0)) "1.0"))
  (is (string= (adhoc/num:nshow (adhoc/num:npow 2 0.5d0)) "1.4142135623730951"))
  (is (typep (adhoc/num:npow 2 0.5d0) 'double-float)))

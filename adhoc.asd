;;;; adhoc.asd

(asdf:defsystem #:adhoc/num
  :description "The ad numeric seam: exact integer/rational arithmetic and display"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "num"
  :components ((:file "package")
               (:file "num")))

(asdf:defsystem #:adhoc/ad
  :description "The ad language front end: lexer, AST, parser"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "ad"
  :components ((:file "package")
               (:file "lexer")
               (:file "ast")
               (:file "parser")))

(asdf:defsystem #:adhoc/interpreter
  :description "Tree-walking evaluator for ad. Disposable: phase 4 replaces this with an interaction-net engine"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "interpreter"
  :depends-on (#:adhoc/num #:adhoc/ad)
  :components ((:file "package")
               (:file "interpreter")))

(asdf:defsystem #:adhoc/repl
  :description "REPL glue for ad: prompt, per-line error recovery, clean exit on EOF"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "repl"
  :depends-on (#:adhoc/num #:adhoc/ad #:adhoc/interpreter)
  :components ((:file "package")
               (:file "repl")))

(asdf:defsystem #:adhoc/cli
  :description "adhoc entry point: argv handling, float format, debugger hook"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "cli"
  :depends-on (#:adhoc/repl)
  :components ((:file "package")
               (:file "cli")))

(asdf:defsystem #:adhoc
  :description "ADhoc Higher Order Calculator -- a cli calculator and language like bc and hoc"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :depends-on (#:adhoc/cli)
  :in-order-to ((asdf:test-op (asdf:test-op #:adhoc/tests))))

(asdf:defsystem #:adhoc/tests
  :description "FiveAM test suites for adhoc"
  :author "George Watson <gigolo@hotmail.co.uk>"
  :license "GPLv3"
  :version "0.1.0"
  :serial t
  :pathname "test"
  :depends-on (#:adhoc/num #:adhoc/ad #:adhoc/interpreter #:fiveam)
  :components ((:file "package")
               (:file "test-num")
               (:file "test-lexer")
               (:file "test-parser")
               (:file "test-interpreter")
               (:file "test-grammar"))
  :perform (asdf:test-op (o s)
             (uiop:symbol-call :fiveam :run! (uiop:find-symbol* :adhoc-suite :adhoc/tests))))

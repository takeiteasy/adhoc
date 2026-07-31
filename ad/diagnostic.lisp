;;;; diagnostic.lisp
;;;;
;;;; Renders a message + caret-pointing source excerpt from a `[start, end)` character span.
;;;; Takes the source text and offsets rather than reading them off a condition, so the same
;;;; renderer works for REPL lines today and multi-line script files in phase 6 -- see
;;;; docs/architecture.md.

(in-package #:adhoc/ad)

(defun %line-bounds (source start)
  "Return (values line-start line-end line-number) for the 0-based line containing offset
START in SOURCE. line-end excludes the terminating newline, if any; line-number is 1-based."
  (let ((line-start 0) (line-no 1) (n (length source)))
    (loop for i from 0 below (min start n)
          when (char= (char source i) #\Newline)
            do (setf line-start (1+ i)) (incf line-no))
    (let ((line-end (or (position #\Newline source :start line-start) n)))
      (values line-start line-end line-no))))

(defun render-diagnostic (stream source label message start end)
  "Write a two-line diagnostic block to STREAM: `< LABEL MESSAGE`, then the source line
containing START (tab-expanded so offsets stay aligned), then a caret line underlining
`[start, end)` clamped to that line. Multi-line SOURCE gets a `N: ` line-number gutter."
  (multiple-value-bind (line-start line-end line-no) (%line-bounds source start)
    (let* ((multiline (find #\Newline source))
           (prefix (if multiline (format nil "~d: " line-no) ""))
           (line-text (substitute #\Space #\Tab (subseq source line-start line-end)))
           (col (- start line-start))
           (span (max 1 (- (min end line-end) start))))
      (format stream "< ~a ~a~%" label message)
      (format stream "    ~a~a~%" prefix line-text)
      (format stream "    ~a~a~a~%"
              (make-string (length prefix) :initial-element #\Space)
              (make-string col :initial-element #\Space)
              (concatenate 'string "^" (make-string (1- span) :initial-element #\~))))))

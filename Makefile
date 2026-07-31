.PHONY: build test clean

build:
	ros build roswell/adhoc.ros

test:
	ros run -- --non-interactive --eval '(ql:quickload :adhoc/tests :silent t)' \
	           --eval '(asdf:test-system :adhoc/tests)'

clean:
	rm -f roswell/adhoc
	find . -name '*.fasl' -delete

#!/usr/bin/make -f

pdfs = $(foreach md,$(shell find * -name '*.md'),build/$(md:.md=.pdf))

all: pdf

pdf:  ${pdfs}

build/%.pdf: %.md
	@mkdir -p "$(dir $@)"
	pandoc -f markdown -t latex $< -o $@ --latex-engine=xelatex

clean:
	rm -rf build

# EOF

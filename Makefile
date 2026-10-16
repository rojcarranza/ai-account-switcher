.PHONY: test lint build install

test:
	python3 -m unittest discover -s tests -t .

lint:
	python3 -m compileall -q src tests

build:
	mkdir -p dist
	python3 -m zipapp src -m "ais.__main__:run" -p "/usr/bin/env python3" -o dist/ais

install: build
	mkdir -p $(HOME)/.local/bin
	if [ -e $(HOME)/.local/bin/ais ]; then mv -f $(HOME)/.local/bin/ais $(HOME)/.local/bin/ais.prev; fi
	cp dist/ais $(HOME)/.local/bin/ais
	chmod 755 $(HOME)/.local/bin/ais

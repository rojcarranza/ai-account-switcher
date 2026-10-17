.PHONY: test lint build install

DIST = dist
SRC := $(shell find src -name '*.py')

test:
	python3 -m unittest discover -s tests -t .

lint:
	python3 -m compileall -q src tests

build: $(DIST)/ais

# file target: an unchanged reinstall must not rebuild (zipapp embeds build time)
$(DIST)/ais: $(SRC)
	mkdir -p "$(DIST)"
	python3 -m zipapp src -m "ais.__main__:run" -p "/usr/bin/env python3" -o "$(DIST)/ais"

install: build
	mkdir -p $(HOME)/.local/bin
	if [ -e $(HOME)/.local/bin/ais ] && ! cmp -s "$(DIST)/ais" $(HOME)/.local/bin/ais; then mv -f $(HOME)/.local/bin/ais $(HOME)/.local/bin/ais.prev; fi
	cp "$(DIST)/ais" $(HOME)/.local/bin/ais
	chmod 755 $(HOME)/.local/bin/ais

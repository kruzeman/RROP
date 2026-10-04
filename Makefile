PYTHON ?= python3
CC ?= cc

.PHONY: demo test clean
demo: build/demo
	./build/demo --peek 0xff0000

build/demo: build/demo.c genesis_recompiler/build.py
	$(PYTHON) -m genesis_recompiler build/demo.bin --build --cc "$(CC)" -o $@

build/demo.c: build/demo.bin $(wildcard genesis_recompiler/*.py) $(wildcard genesis_recompiler/*.h)
	$(PYTHON) -m genesis_recompiler $< -o $@ --report build/demo.json

build/demo.bin: examples/make_demo.py
	mkdir -p build
	$(PYTHON) $< $@

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build

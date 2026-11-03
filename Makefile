VENV := .venv/bin/python

.venv:
	python3 -m venv .venv
	$(VENV) -m pip install -q pytest pytest-asyncio

test: .venv
	$(VENV) -m pytest tests/

.PHONY: test

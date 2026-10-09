PY ?= python3

.PHONY: test gate checkup checkup-quick

test:
	$(PY) -m pytest tests/ -q

gate:
	$(PY) -m testbench.gate run

checkup:
	$(PY) -m final_checkup.checkup --full

checkup-quick:
	$(PY) -m final_checkup.checkup --quick

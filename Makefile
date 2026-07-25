PYTHON ?= python

.PHONY: test demo smoke train-ml demo-ml simulate simulate-burst simulate-compare

test:
	PYTHONPATH=src $(PYTHON) -m pytest

demo:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo

smoke:
	PYTHONPATH=src sh scripts/smoke_test.sh

train-ml:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.training train

demo-ml: train-ml
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo \
		--classifier ml \
		--classifier-model artifacts/models/intent-classifier.joblib

simulate:
	PYTHONPATH=src $(PYTHON) -m simulation.cli baseline --seed 42

simulate-burst:
	PYTHONPATH=src $(PYTHON) -m simulation.cli burst --seed 42

simulate-compare:
	PYTHONPATH=src $(PYTHON) -m simulation.cli compare --seed 42

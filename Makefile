.PHONY: test demo smoke

test:
	PYTHONPATH=src python -m pytest

demo:
	PYTHONPATH=src python -m ticket_automation.cli demo

smoke:
	PYTHONPATH=src sh scripts/smoke_test.sh

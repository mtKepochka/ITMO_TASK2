.PHONY: test demo smoke

test:
	pytest

demo:
	python -m ticket_automation.cli demo

smoke:
	sh scripts/smoke_test.sh

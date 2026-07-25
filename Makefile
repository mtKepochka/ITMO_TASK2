PYTHON ?= python
IMAGE ?= ticket-automation
VERSION := $(shell PYTHONPATH=src $(PYTHON) -c "import ticket_automation; print(ticket_automation.__version__)")
REVISION := $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
DEPLOY_TAG := $(VERSION)-$(REVISION)

.PHONY: test demo smoke train-ml demo-ml simulate simulate-burst simulate-compare \
	docker-build container-demo container-train-ml container-demo-ml deploy \
	deploy-ml update update-ml

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

docker-build:
	docker build --pull \
		--build-arg APP_VERSION=$(VERSION) \
		--build-arg VCS_REF=$(REVISION) \
		--tag $(IMAGE):$(DEPLOY_TAG) \
		--tag $(IMAGE):$(VERSION) \
		--tag $(IMAGE):latest \
		.

container-demo: docker-build
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose run --rm demo

container-train-ml: docker-build
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose run --rm train-ml

container-demo-ml:
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose run --rm demo-ml

deploy: docker-build
	docker run --rm $(IMAGE):$(DEPLOY_TAG) --version

deploy-ml: deploy
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose run --rm train-ml
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose run --rm demo-ml

update:
	git pull --ff-only
	$(MAKE) deploy

update-ml:
	git pull --ff-only
	$(MAKE) deploy-ml

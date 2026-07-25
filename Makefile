PYTHON ?= python
IMAGE ?= ticket-automation
VERSION := $(shell PYTHONPATH=src $(PYTHON) -c "import ticket_automation; print(ticket_automation.__version__)")
REVISION := $(shell git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)
DEPLOY_TAG := $(VERSION)-$(REVISION)

.PHONY: test demo demo-rules demo-auto demo-ml demo-semantic api benchmark \
	benchmark-fault smoke train-ml simulate simulate-burst simulate-compare \
	docker-build container-demo container-api container-train-ml \
	container-demo-ml deploy \
	deploy-ml update update-ml

test:
	PYTHONPATH=src $(PYTHON) -m pytest

demo: train-ml
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo \
		--classifier ml \
		--classifier-model artifacts/models/intent-classifier.joblib

demo-rules:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo

demo-auto: train-ml
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo \
		--classifier ml \
		--classifier-model artifacts/models/intent-classifier.joblib \
		--rollout-config config/rollout.auto-demo.json

demo-ml: demo

demo-semantic: train-ml
	PYTHONPATH=src $(PYTHON) -m ticket_automation.cli demo \
		--classifier ml \
		--classifier-model artifacts/models/intent-classifier.joblib \
		--retriever e5

api:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.api

benchmark:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.benchmark \
		--tickets 1000 --concurrency 20

benchmark-fault:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.benchmark \
		--tickets 1000 --concurrency 20 --failure-every 10

smoke:
	PYTHONPATH=src sh scripts/smoke_test.sh

train-ml:
	PYTHONPATH=src $(PYTHON) -m ticket_automation.training train

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

container-api: docker-build
	TICKET_IMAGE=$(IMAGE) TICKET_TAG=$(DEPLOY_TAG) TICKET_VERSION=$(VERSION) \
		TICKET_REVISION=$(REVISION) docker compose up api

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

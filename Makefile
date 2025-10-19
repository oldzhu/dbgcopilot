PYTHON := python
BUILD_DIR := dist

.PHONY: build install-wheel test-smoke clean

build:
	$(PYTHON) -m build

install-wheel: build
	# install the latest wheel into the active environment
	pip install --upgrade --force-reinstall $(BUILD_DIR)/*.whl

test-smoke: install-wheel
	# print plugin path and ensure the console script works
	dbgcopilot-plugin-path

clean:
	rm -rf build $(BUILD_DIR) *.egg-info
IMAGE ?= dbgcopilot-dev:latest
WORKDIR ?= /workspace

.PHONY: help docker-build docker-shell docker-pytest gdb-shell lldb-shell

help:
	@echo "Targets:"
	@echo "  docker-build   - Build the dev image ($(IMAGE))"
	@echo "  docker-shell   - Start an interactive shell in the dev container"
	@echo "  docker-pytest  - Run pytest inside the dev container"
	@echo "  gdb-shell      - Start gdb inside the dev container"
	@echo "  lldb-shell     - Start lldb inside the dev container"

docker-build:
	docker build -t $(IMAGE) .

docker-shell:
	docker run --rm -it -v $(PWD):$(WORKDIR) -w $(WORKDIR) $(IMAGE) bash

docker-pytest:
	docker run --rm -it -v $(PWD):$(WORKDIR) -w $(WORKDIR) $(IMAGE) python3 -m pytest -q

gdb-shell:
	docker run --rm -it -v $(PWD):$(WORKDIR) -w $(WORKDIR) --cap-add=SYS_PTRACE --security-opt seccomp=unconfined $(IMAGE) gdb

lldb-shell:
	docker run --rm -it -v $(PWD):$(WORKDIR) -w $(WORKDIR) --cap-add=SYS_PTRACE --security-opt seccomp=unconfined $(IMAGE) lldb
IMAGE := dbgcopilot-dev:latest

.PHONY: docker-build docker-shell docker-test demo-build demo-run

docker-build:
	docker build -t $(IMAGE) .

docker-shell:
	docker run --rm -it -v $(PWD):/workspace -w /workspace $(IMAGE) bash

docker-test:
	docker run --rm -v $(PWD):/workspace -w /workspace $(IMAGE) bash -lc "python3 -m pytest -q"

demo-build:
	$(MAKE) -C examples/crash_demo build

demo-run:
	$(MAKE) -C examples/crash_demo run

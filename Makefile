PYTHON_VERSION ?= 3.12
HYPERFRAMES_VERSION := 0.8.40
VENV_DIR ?= .venv
BASE_PYTHON ?= $(shell command -v python$(PYTHON_VERSION) 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
RUN_PYTHON = $(shell for dir in "$$VIRTUAL_ENV" "$$CONDA_PREFIX" "$(VENV_DIR)"; do if [ -n "$$dir" ] && [ -x "$$dir/bin/python" ]; then printf "%s/bin/python" "$$dir"; exit 0; elif [ -n "$$dir" ] && [ -x "$$dir/Scripts/python.exe" ]; then printf "%s/Scripts/python.exe" "$$dir"; exit 0; fi; done; if [ "$(OS)" = "Windows_NT" ]; then printf "%s/Scripts/python.exe" "$(VENV_DIR)"; else printf "%s/bin/python" "$(VENV_DIR)"; fi)
PIP = $(RUN_PYTHON) -m pip

.DEFAULT_GOAL := setup

.PHONY: setup install install-dev install-gpu test test-contracts test-qa lint clean preflight runtime-preflight audit demo demo-list hyperframes-doctor hyperframes-warm venv ensure-venv

# ---- Virtual environment ----

ensure-venv:
	@if [ -n "$$VIRTUAL_ENV" ] && { [ -x "$$VIRTUAL_ENV/bin/python" ] || [ -x "$$VIRTUAL_ENV/Scripts/python.exe" ]; }; then \
		echo "==> Using active virtual environment: $$VIRTUAL_ENV"; \
	elif [ -n "$$CONDA_PREFIX" ] && { [ -x "$$CONDA_PREFIX/bin/python" ] || [ -x "$$CONDA_PREFIX/Scripts/python.exe" ]; }; then \
		echo "==> Using active conda environment: $$CONDA_PREFIX"; \
	elif [ -x "$(VENV_DIR)/bin/python" ] || [ -x "$(VENV_DIR)/Scripts/python.exe" ]; then \
		echo "==> Using existing virtual environment: $(VENV_DIR)"; \
	elif command -v uv >/dev/null 2>&1; then \
		echo "==> Creating virtual environment with uv (Python $(PYTHON_VERSION)+): $(VENV_DIR)"; \
		uv venv --python $(PYTHON_VERSION) "$(VENV_DIR)"; \
	else \
		if [ -z "$(BASE_PYTHON)" ]; then \
			echo "ERROR: Python $(PYTHON_VERSION)+ is required, but no python executable was found."; \
			exit 1; \
		fi; \
		"$(BASE_PYTHON)" -c "import sys; required=tuple(map(int, '$(PYTHON_VERSION)'.split('.')[:2])); raise SystemExit(0 if sys.version_info[:2] >= required else 1)" || { \
			echo "ERROR: OpenMontage requires Python $(PYTHON_VERSION)+."; \
			echo "Install uv or Python $(PYTHON_VERSION)+, then run make again."; \
			exit 1; \
		}; \
		echo "==> Creating virtual environment with Python venv: $(VENV_DIR)"; \
		"$(BASE_PYTHON)" -m venv "$(VENV_DIR)" || { \
			echo "ERROR: Could not create $(VENV_DIR). Install uv or ensure python venv support is available."; \
			exit 1; \
		}; \
	fi
	@$(RUN_PYTHON) -c "import sys; required=tuple(map(int, '$(PYTHON_VERSION)'.split('.')[:2])); raise SystemExit(0 if sys.version_info[:2] >= required else 1)" || { \
		echo "ERROR: OpenMontage requires Python $(PYTHON_VERSION)+."; \
		echo "Current interpreter is $$($(RUN_PYTHON) -c 'import sys; print(\".\".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo unavailable): $(RUN_PYTHON)"; \
		echo "Activate a compatible environment or remove it so make can create $(VENV_DIR)."; \
		exit 1; \
	}
	@$(RUN_PYTHON) -m pip --version >/dev/null 2>&1 || $(RUN_PYTHON) -m ensurepip --upgrade >/dev/null
	@$(RUN_PYTHON) -c "import pip; assert pip.__version__ == '26.2.1'" 2>/dev/null || $(PIP) install --require-hashes -r requirements-bootstrap.lock

venv: ensure-venv
	@echo "==> Virtual environment ready."
	@echo "    Python: $(RUN_PYTHON)"
	@if [ -z "$$VIRTUAL_ENV" ] && [ -z "$$CONDA_PREFIX" ]; then if [ "$(OS)" = "Windows_NT" ]; then echo "    Activate with: $(VENV_DIR)\\Scripts\\Activate.ps1"; else echo "    Activate with: source $(VENV_DIR)/bin/activate"; fi; fi

# ---- One-command setup ----

setup: ensure-venv
	@echo "==> Installing Python dependencies..."
	$(PIP) install --require-hashes -r requirements.lock
	@echo ""
	@echo "==> Installing Remotion composer..."
	cd remotion-composer && npm ci
	@echo ""
	@echo "==> Optional local TTS/model runtimes are installed separately after preflight."
	@echo "==> HyperFrames is optional. Run 'make hyperframes-warm' to install version $(HYPERFRAMES_VERSION)."
	@echo ""
	@echo "Done! Open this project in your AI coding assistant and start creating."
	@echo "  Supply credentials through your trusted launcher/secret manager. No .env was created."
	@echo "  Optional: run 'make install-gpu' if you have an NVIDIA GPU."
	@echo "  Optional: run 'make hyperframes-doctor' to fully validate the HyperFrames runtime."
	@echo "  Run 'make preflight' for a passive configuration inventory (not a live-provider check)."

# ---- Individual installs ----

install: ensure-venv
	$(PIP) install --require-hashes -r requirements.lock

install-dev: ensure-venv
	$(PIP) install --require-hashes -r requirements-dev.lock

install-gpu: ensure-venv
	$(PIP) install -r requirements-gpu.txt
	$(PIP) install diffusers transformers accelerate

# ---- Testing ----

test: ensure-venv
	$(RUN_PYTHON) -m pytest tests/ -v

test-contracts: ensure-venv
	$(RUN_PYTHON) -m pytest tests/contracts/ -v

test-qa: ensure-venv
	$(RUN_PYTHON) scripts/run_local_qa.py

# ---- Utilities ----

preflight:
	$(RUN_PYTHON) -c "from tools.tool_registry import registry; import json; print(json.dumps(registry.configuration_inventory(), indent=2))"

runtime-preflight: ensure-venv
	$(RUN_PYTHON) -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"

audit: ensure-venv
	$(RUN_PYTHON) -m pip_audit --disable-pip --no-deps -r requirements.lock
	cd remotion-composer && npm audit --omit=dev

hyperframes-doctor: ensure-venv
	@echo "==> Probing HyperFrames runtime (node/ffmpeg/npx + hyperframes doctor)..."
	$(RUN_PYTHON) -c "from tools.video.hyperframes_compose import HyperFramesCompose; r=HyperFramesCompose().execute({'operation':'doctor'}); import json; print(json.dumps(r.data, indent=2)); print('OK' if r.success else f'FAIL: {r.error}')"

hyperframes-warm:
	@echo "==> Installing approved HyperFrames runtime $(HYPERFRAMES_VERSION)..."
	npx --yes hyperframes@$(HYPERFRAMES_VERSION) --version
	@echo "==> Cache warm complete."

demo: ensure-venv
	@echo "==> Rendering zero-key demo videos (no API keys needed)..."
	@echo "    These use only Remotion components — animated charts, text, data viz."
	@echo ""
	$(RUN_PYTHON) render_demo.py

demo-list: ensure-venv
	$(RUN_PYTHON) render_demo.py --list

lint: ensure-venv
	$(RUN_PYTHON) -m compileall -q lib tools backlot schemas styles

clean:
	$(BASE_PYTHON) -c "import pathlib, shutil; excluded=[pathlib.Path('$(VENV_DIR)'), pathlib.Path('venv')]; skip=lambda p: any(p == root or root in p.parents for root in excluded); roots=[p for p in pathlib.Path('.').rglob('__pycache__') if not skip(p)]; [shutil.rmtree(p) for p in roots]; files=[p for p in pathlib.Path('.').rglob('*.pyc') if not skip(p)]; [p.unlink() for p in files]"

.PHONY: help install install-dev clean cython compile build test test-unit test-integration lint format check-format check-lint check-all release

# Default target
.DEFAULT_GOAL := help

# Python interpreter
PYTHON ?= python3
PIP ?= pip

# Project configuration
PROJECT_NAME := blacksheep
PACKAGE_DIR := blacksheep
TEST_DIRS := tests itests

# Cython source files
CYTHON_SOURCES := \
	$(PACKAGE_DIR)/url.pyx \
	$(PACKAGE_DIR)/exceptions.pyx \
	$(PACKAGE_DIR)/headers.pyx \
	$(PACKAGE_DIR)/cookies.pyx \
	$(PACKAGE_DIR)/contents.pyx \
	$(PACKAGE_DIR)/messages.pyx \
	$(PACKAGE_DIR)/scribe.pyx \
	$(PACKAGE_DIR)/baseapp.pyx

# Generated C files
CYTHON_C_FILES := $(CYTHON_SOURCES:.pyx=.c)

# Help information
help: ## Show this help message
	@echo "BlackSheep Build Tools"
	@echo ""
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Install dependencies
install: ## Install production dependencies
	$(PIP) install -e .

install-dev: ## Install development dependencies
	$(PIP) install -e ".[dev]"

# Clean build artifacts
clean: ## Clean all build artifacts
	@echo "🧹 Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -f $(CYTHON_C_FILES)
	find . -name "*.so" -delete
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleanup completed"

# Cython compilation
cython: $(CYTHON_C_FILES) ## Compile Cython files to C

$(PACKAGE_DIR)/%.c: $(PACKAGE_DIR)/%.pyx
	@echo "🔨 Compiling Cython: $<"
	cython $<

# Build extensions
compile: cython ## Compile Cython extensions to shared libraries
	@echo "🏗️  Building extension modules..."
	$(PYTHON) setup.py build_ext --inplace
	@echo "✅ Extension build completed"

# Build distribution packages
build: clean cython ## Build distribution packages (wheel and sdist)
	@echo "📦 Building distribution packages..."
	$(PYTHON) -m build
	@echo "✅ Distribution packages build completed"

# Run tests
test: test-unit test-integration ## Run all tests

test-unit: compile ## Run unit tests
	@echo "🧪 Running unit tests..."
	pytest tests/ -v

test-integration: compile ## Run integration tests
	@echo "🧪 Running integration tests..."
	pytest itests/ -v

test-cov: compile ## Run tests with coverage report
	@echo "🧪 Running tests with coverage..."
	pytest $(TEST_DIRS) --cov=$(PACKAGE_DIR) --cov-report=html --cov-report=term

# Code quality checks
lint: ## Run code linting
	@echo "🔍 Running code linting..."
	flake8 $(PACKAGE_DIR) $(TEST_DIRS)
	@echo "✅ Code linting passed"

format: ## Format code
	@echo "✨ Formatting code..."
	black $(PACKAGE_DIR) $(TEST_DIRS)
	isort $(PACKAGE_DIR) $(TEST_DIRS)
	@echo "✅ Code formatting completed"

check-format: ## Check code formatting
	@echo "🔍 Checking code formatting..."
	black --check --diff $(PACKAGE_DIR) $(TEST_DIRS)
	isort --check-only --diff $(PACKAGE_DIR) $(TEST_DIRS)
	@echo "✅ Code formatting check passed"

check-lint: ## Check code style (without modifying files)
	@echo "🔍 Checking code style..."
	flake8 $(PACKAGE_DIR) $(TEST_DIRS)
	@echo "✅ Code style check passed"

check-all: check-format check-lint ## Run all checks

# Cython annotation generation (for performance analysis)
annotate: ## Generate Cython annotation HTML files
	@echo "📊 Generating Cython annotations..."
	@for pyx_file in $(CYTHON_SOURCES); do \
		echo "  Generating annotation for $$pyx_file..."; \
		cython $$pyx_file -a; \
	done
	@echo "✅ Cython annotation generation completed"

# Development environment setup
dev-setup: clean install-dev ## Setup development environment
	@echo "🚀 Development environment setup completed"
	@echo "   Run 'make compile' to build extensions"
	@echo "   Run 'make test' to run tests"

# Release related
release-test: clean build ## Release to Test PyPI
	@echo "🚀 Releasing to Test PyPI..."
	twine upload --repository testpypi dist/*

release: clean build ## Release to PyPI
	@echo "🚀 Releasing to PyPI..."
	twine upload dist/*

# Performance tests
perf: compile ## Run performance tests
	@echo "⚡ Running performance tests..."
	$(PYTHON) -m pytest perf/ -v

# Check build environment
check-env: ## Check build environment
	@echo "🔍 Checking build environment..."
	@echo "Python: $(shell $(PYTHON) --version)"
	@echo "Pip: $(shell $(PIP) --version)"
	@echo "Cython: $(shell cython --version 2>/dev/null || echo 'Not installed')"
	@echo "Black: $(shell black --version 2>/dev/null || echo 'Not installed')"
	@echo "Isort: $(shell isort --version 2>/dev/null || echo 'Not installed')"
	@echo "Flake8: $(shell flake8 --version 2>/dev/null || echo 'Not installed')"
	@echo "Pytest: $(shell pytest --version 2>/dev/null || echo 'Not installed')"

# Watch mode (requires watchdog)
watch: ## Watch file changes and auto-recompile
	@echo "👀 Watching file changes..."
	@command -v watchmedo >/dev/null 2>&1 || { echo "Need to install watchdog: pip install watchdog"; exit 1; }
	watchmedo auto-restart --patterns="*.pyx;*.py" --recursive --signal SIGTERM \
		$(PYTHON) setup.py build_ext --inplace

# Documentation generation (if available)
docs: ## Generate documentation
	@echo "📚 Generating documentation..."
	@echo "Documentation generation not yet implemented"

# Version information
version: ## Show version information
	@echo "📋 Version information:"
	@$(PYTHON) -c "import $(PACKAGE_DIR); print(f'$(PROJECT_NAME): {$(PACKAGE_DIR).__version__}')"

# Backward compatibility targets
cyt: cython ## Backward compatibility: compile Cython files

buildext: compile ## Backward compatibility: build extensions

init: install ## Backward compatibility: install dependencies

test-v: test-unit ## Backward compatibility: verbose testing

itest: test-integration ## Backward compatibility: integration testing

prepforbuild: ## Backward compatibility: prepare for build
	pip install --upgrade build

testrelease: release-test ## Backward compatibility: test release

artifacts: build ## Backward compatibility: build artifacts

test-cov-unit: ## Backward compatibility: unit test coverage
	pytest --cov-report html --cov=blacksheep tests/

check-flake8: ## Backward compatibility: flake8 check
	@echo "🔍 Checking flake8..."
	@flake8 blacksheep tests itests

check-isort: ## Backward compatibility: isort check
	@echo "🔍 Checking isort..."
	@isort --check-only blacksheep tests itests

check-black: ## Backward compatibility: black check
	@echo "🔍 Checking black..."
	@black --check blacksheep tests itests
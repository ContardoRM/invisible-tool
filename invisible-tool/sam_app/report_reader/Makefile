COMMON_DIR := $(abspath $(dir $(firstword $(MAKEFILE_LIST)))/../common)

build-ReportReaderFunction:
	python3 -m pip install -r requirements.txt --target "$(ARTIFACTS_DIR)" --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 --only-binary=:all:
	cp app.py "$(ARTIFACTS_DIR)/"
	mkdir -p "$(ARTIFACTS_DIR)/common"
	cp "$(COMMON_DIR)/__init__.py" "$(ARTIFACTS_DIR)/common/"
	cp "$(COMMON_DIR)/report_store.py" "$(ARTIFACTS_DIR)/common/"

.PHONY: load ratios screener test lint format coverage report dashboard api clean

# Runs ETL: loads all 12 files into nifty100.db. Re-runnable (idempotent).
load:
	python3 src/etl/loader.py

# Runs Ratio Engine: computes 50+ KPIs and populates financial_ratios.
ratios:
	python3 src/analytics/populate_financial_ratios.py

# Runs Screener + Peer Engine: screener_output.xlsx, peer_comparison.xlsx,
# peer_percentiles table, radar charts. Requires `make load` and
# `make ratios` to have already run.
screener:
	python3 src/screener/run_sprint3.py

# Runs the full pytest suite with coverage (same command CI runs).
test:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=80

# Lints with ruff.
lint:
	ruff check src tests

# Checks formatting with black (use `black src tests` to auto-fix).
format:
	black --check src tests

# Generates HTML + XML coverage reports (htmlcov/index.html, coverage.xml).
coverage:
	pytest tests/ --cov=src --cov-report=html --cov-report=xml

# Generates all PDF/Excel reports. (Sprint 5 — not yet built)
report:
	@echo "Reporting engine is a Sprint 5 deliverable — not yet implemented."
	@exit 1

# Starts the Streamlit dashboard. (Sprint 5 — not yet built)
dashboard:
	@echo "Dashboard is a Sprint 5 deliverable — not yet implemented."
	@exit 1

# Starts the FastAPI/Uvicorn server. (Sprint 6 — not yet built)
api:
	@echo "API layer is a Sprint 6 deliverable — not yet implemented."
	@exit 1

# Deletes .pyc files, __pycache__, and test/coverage artifacts (NOT the database).
clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

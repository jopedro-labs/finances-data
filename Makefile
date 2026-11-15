.PHONY: install check lint lint-fix type test run-yahoo-health run-just-etf-bot run-yahoo-bot

install:
	python3 -m pip install -e ".[dev]"

lint:
	python3 -m ruff check finances_data data

lint-fix:
	python3 -m ruff check finances_data data --fix

type:
	python3 -m mypy finances_data data

test:
	python3 -m pytest --tb=short

check: lint type test

quality-eval-agent:
	python3 scripts/quality_eval_agent.py

run-just-etf-bot:
	act workflow_dispatch \
		-W .github/just_etf_bot.yml \
		--secret-file .env \
		--verbose

run-yahoo-bot:
	act workflow_dispatch \
		-W .github/yahoo_bot.yml \
		--secret-file .env \
		--verbose

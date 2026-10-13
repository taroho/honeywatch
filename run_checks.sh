#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/ryutaroyamashita/taroho/honeywatch
{
  echo "=== mypy ==="
  uv run mypy src/honeywatch/detection/classifier.py
  echo "MYPY_EXIT=$?"
  echo "=== ruff ==="
  uv run ruff check src/honeywatch/detection/classifier.py
  echo "RUFF_EXIT=$?"
  echo "=== pytest ==="
  uv run pytest tests/test_detection -q
  echo "PYTEST_EXIT=$?"
} > checks_out.txt 2>&1

#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/ryutaroyamashita/taroho/honeywatch
{
  echo "=== pytest ==="
  uv run pytest tests/test_analysis/test_geoip.py -q
  echo "PYTEST_EXIT=$?"
  echo "=== mypy ==="
  uv run mypy src/honeywatch/analysis/geoip.py
  echo "MYPY_EXIT=$?"
  echo "=== ruff ==="
  uv run ruff check src/honeywatch/analysis/geoip.py tests/test_analysis/test_geoip.py
  echo "RUFF_EXIT=$?"
} > geoip_checks_out.txt 2>&1

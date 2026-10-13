#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/ryutaroyamashita/taroho/honeywatch
{
  echo "=== versions ==="
  uv pip list | grep -Ei "aiohttp|hypothesis|structlog|pytest"
  echo "EXIT=$?"
} > inspect_env.txt 2>&1

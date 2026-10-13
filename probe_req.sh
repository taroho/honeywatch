#!/usr/bin/env bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/ryutaroyamashita/taroho/honeywatch
{
  uv run python probe_req.py
  echo "EXIT=$?"
} > probe_req.txt 2>&1

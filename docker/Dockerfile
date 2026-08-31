# HoneyWatch Python バックエンド用 Dockerfile
# マルチステージビルド: 依存インストール → 実行環境

FROM python:3.12-slim AS base

# セキュリティ: 非 root ユーザーで実行
RUN groupadd -r honeywatch && useradd -r -g honeywatch honeywatch

WORKDIR /app

# システム依存パッケージ（PostgreSQL クライアントライブラリ）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# --- 依存インストールステージ ---
FROM base AS deps

# uv インストール
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 依存ファイルのみ先にコピー（キャッシュ最適化）
COPY pyproject.toml uv.lock* ./

# 依存インストール（プロジェクト自体は含めない）
RUN uv sync --no-dev --no-install-project

# --- 実行ステージ ---
FROM base AS runtime

# 仮想環境をコピー
COPY --from=deps /app/.venv /app/.venv

# ソースコードをコピー
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY config/ ./config/
COPY alembic.ini ./

# PATH に仮想環境を追加
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# データディレクトリ作成
RUN mkdir -p /app/data/ssh_host_keys && \
    chown -R honeywatch:honeywatch /app

USER honeywatch

# デフォルトコマンド（docker-compose で上書きされる）
CMD ["uvicorn", "honeywatch.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

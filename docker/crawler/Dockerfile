FROM python:3.12-slim

WORKDIR /app

# Install uv (single static binary, no deps)
RUN pip install --no-cache-dir "uv>=0.4"

# Cache dependency install layer
COPY pyproject.toml uv.lock ./
RUN uv sync --extra crawler --frozen --no-dev

# Application code
COPY crawler/ ./crawler/
COPY config/ ./config/

# Output dir is bind-mounted at runtime
VOLUME ["/app/raw_cache"]

ENTRYPOINT ["uv", "run", "python", "-m", "crawler"]

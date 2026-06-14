FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv && \
    rm -rf /root/.cache/pip

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project --verbose && \
    uv cache clean

COPY src/ src/
COPY configs/ /app/configs/

RUN uv sync --frozen --no-dev --verbose

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

ENTRYPOINT ["trading"]
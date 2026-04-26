# fs_mpc_mg base image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for matplotlib (used by report+demos)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libfreetype6 libfontconfig1 && \
    rm -rf /var/lib/apt/lists/*

# Install package with mqtt + dev extras
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install -e .[mqtt]

COPY tests/ ./tests/
COPY scripts/ ./scripts/

# Default shows entrypoint usage
CMD ["python", "-c", "print('Use docker-compose service entrypoint: ica | cmc | dt | dashboard')"]

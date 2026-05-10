# SAMBPS DTaaS Protection-Validation v1.0 — minimal Dockerfile.
#
# Build (from the project root, NOT this docker/ subdirectory):
#
#   docker build -f dtaas/protection_validation/docker/Dockerfile \
#                -t sambps/protection-validation:v1.0 .
#
# Run:
#
#   docker run --rm -p 8080:8080 sambps/protection-validation:v1.0
#
# Image-size budget: < 200 MB.  Achieved by:
#  - python:3.12-slim base (~ 45 MB);
#  - numpy + scipy + click only (~ 80 MB combined);
#  - source tree without the heavy outputs/ artefacts (excluded
#    via .dockerignore).
#
# Note: this Dockerfile is committed but the image is NOT built or
# pushed in the WP5.4 commit; the push is gated on explicit PI green-
# light per the WP5.4 brief.

# syntax=docker/dockerfile:1.6

FROM python:3.12-slim AS builder

WORKDIR /build

# Build wheel of the sambp_fault_location_id package itself.
COPY pyproject.toml /build/
COPY README.md      /build/
COPY LICENSE        /build/
COPY src            /build/src
RUN  pip install --no-cache-dir build \
  && python -m build --wheel --no-isolation --outdir /build/dist

# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="SAMBPS DTaaS Protection-Validation"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/SAMBPS-DTaaS/HIF-TF-Locator"
LABEL org.opencontainers.image.description="\
HIF-locator REST API + scenario-engine plugin + identifiability /\
CRLB UI widget.  See dtaas/protection_validation/README.md."

WORKDIR /app

# Install runtime deps + the locally-built wheel.
COPY --from=builder /build/dist/*.whl /tmp/
RUN  pip install --no-cache-dir /tmp/*.whl click \
  && rm -rf /tmp/*.whl /root/.cache

# Copy the UI assets.
COPY dtaas/protection_validation/ui /app/ui

EXPOSE 8080

# Run the API server.
CMD ["python", "-m", "sambp_fault_location_id.dtaas.protection_validation.api"]

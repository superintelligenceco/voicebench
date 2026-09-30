# syntax=docker/dockerfile:1
# Container image for the voicebench CLI with the core adapters (mock, websocket).
# Build: docker build -t voicebench .
# Run:   docker run --rm -v "$PWD:/work" voicebench run scenario.yaml

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist

FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
LABEL org.opencontainers.image.source="https://github.com/superintelligenceco/voicebench" \
      org.opencontainers.image.description="Benchmark harness for real-time voice agents" \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /dist /tmp/dist
RUN python -m pip install --no-cache-dir /tmp/dist/*.whl \
    && rm -rf /tmp/dist \
    && useradd --create-home --uid 10001 voicebench \
    && mkdir /work && chown voicebench /work
USER voicebench
WORKDIR /work
ENTRYPOINT ["voicebench"]
CMD ["--help"]

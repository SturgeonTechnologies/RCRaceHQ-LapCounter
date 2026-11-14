# Lap counter app image: one image, several services (web, lapd, syncd; later
# announcerd), chosen by the command in compose.yaml. Built for linux/arm64 (Pi 4).
FROM python:3.12-slim-bookworm AS build
WORKDIR /src
COPY pyproject.toml ./
COPY lapcounter ./lapcounter
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LAPCOUNTER_DB=/var/lib/lapcounter/lapcounter.db \
    OPENSTINT_ZMQ=tcp://127.0.0.1:5556
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels lapcounter \
 && apt-get update && apt-get install -y --no-install-recommends libcap2-bin \
 && rm -rf /var/lib/apt/lists/* \
 && setcap cap_net_bind_service=+ep "$(readlink -f "$(command -v python)")" \
 && useradd --system --uid 10001 --home-dir /var/lib/lapcounter --shell /usr/sbin/nologin lapcounter \
 && install -d -o lapcounter -g lapcounter -m 0750 /var/lib/lapcounter
USER lapcounter
VOLUME ["/var/lib/lapcounter"]
# Port 80 so the hotspot captive-portal check reaches it; the python binary
# carries cap_net_bind_service (set above) so the non-root user can bind it.
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:80/healthz', timeout=2)" || exit 1
# gthread: the live view is a long-lived SSE stream per browser tab.
CMD ["gunicorn", "--worker-class", "gthread", "--workers", "2", "--threads", "16", \
     "--bind", "0.0.0.0:80", "--access-logfile", "-", "lapcounter.web:create_app()"]

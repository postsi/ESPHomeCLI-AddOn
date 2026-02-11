# ESPHomeCLI AddOn - ESPHome CLI Web API
# Base = same image as official ESPHome addon (esphome-hassio). It uses uv for pip.
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install our deps the same way the ESPHome image does (uv pip install)
RUN uv pip install --no-cache-dir fastapi uvicorn

WORKDIR /app
COPY app/ /app/

# Addon data dir for temp files and options
ENV DATA_DIR=/data
EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]

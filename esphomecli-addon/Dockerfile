# ESPHomeCLI AddOn - ESPHome CLI Web API
# Base has esphome CLI; we add FastAPI and our app.
ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN pip3 install --no-cache-dir fastapi uvicorn

WORKDIR /app
COPY app/ /app/

# Addon data dir for temp files and options
ENV DATA_DIR=/data
EXPOSE 8099

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8099"]

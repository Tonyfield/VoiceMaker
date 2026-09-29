ARG APP_INFRA_IMAGE=tts-voice-cloner-infra:latest

FROM ${APP_INFRA_IMAGE}

WORKDIR /app

COPY src ./src
COPY config.yaml ./config.yaml
COPY model-profiles.yaml ./model-profiles.yaml
COPY README.md ./README.md

RUN mkdir -p /app/data /app/log /app/models

EXPOSE 20100

CMD ["python", "-m", "src.main", "serve"]
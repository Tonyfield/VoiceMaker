ARG MODEL_INFRA_IMAGE=tts-model-infra:latest

FROM ${MODEL_INFRA_IMAGE}

ARG REQUIREMENTS_FILE=requirements-model-index-extra.txt

WORKDIR /app
COPY requirements*.txt ./

RUN if [ -s "${REQUIREMENTS_FILE}" ]; then pip install -r "${REQUIREMENTS_FILE}"; fi

COPY src ./src
COPY config.yaml ./config.yaml
COPY model-profiles.yaml ./model-profiles.yaml
COPY README.md ./README.md

RUN mkdir -p /app/data /app/log /app/models

EXPOSE 20200

CMD ["python", "-m", "src.main", "serve-model"]
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE}

ARG REQUIREMENTS_FILE=requirements.txt

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    COQUI_TOS_AGREED=1

WORKDIR /opt/voicecloner

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        libglib2.0-0 \
        libgomp1 \
        libsndfile1 \
        libsm6 \
        libxext6 \
        procps \
        tini \
        unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements*.txt /tmp/

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r "/tmp/${REQUIREMENTS_FILE}" \
    && rm -f /tmp/requirements*.txt
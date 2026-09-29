FROM vllm/vllm-omni:v0.28.0

RUN python -m pip install --upgrade pip
RUN pip install "vllm-omni[indextts2]"
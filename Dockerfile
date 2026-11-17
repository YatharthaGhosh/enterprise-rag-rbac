FROM python:3.12-slim
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
# CPU-only PyTorch keeps the image ~2 GB smaller than the default CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .
COPY ui ./ui
COPY scripts ./scripts
COPY eval ./eval
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]

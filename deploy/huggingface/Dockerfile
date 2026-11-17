# Hugging Face Space image: FastAPI (internal :8000) + Streamlit (public :7860) in one container.
FROM python:3.12-slim

# Spaces run as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed
WORKDIR /home/user/app

# CPU-only PyTorch (Docling needs it) keeps the image ~2 GB smaller than the CUDA build
RUN pip install --user torch --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user pyproject.toml README.md ./
COPY --chown=user app ./app
RUN pip install --user .
COPY --chown=user . .

# Build the index at image build time: parses the documents and downloads the Docling,
# embedding and reranker models into the image, so the Space starts ready to answer.
RUN python scripts/ingest.py && python -c "from app.retrieval import _reranker; _reranker()"

ENV DEMO_MODE=true API_URL=http://127.0.0.1:8000
EXPOSE 7860
CMD ["bash", "start.sh"]

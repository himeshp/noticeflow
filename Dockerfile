# NoticeFlow demo cockpit — FastAPI (pipeline in-process) + built React SPA,
# one container / one public URL. Built by Cloud Build for Cloud Run.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching, then the package (editable so api.py's
# REPO_ROOT = parents[2] resolves to /app and finds data/ + frontend/dist, and
# so `python -m noticeflow.mcp.erp_server` works as the MCP stdio subprocess).
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Runtime assets: sample notices (the cockpit's /api/samples), the source PDFs +
# their page index (the /api/source viewer), and the SPA build.
COPY data/sample_notices/ ./data/sample_notices/
COPY data/source_pdfs/ ./data/source_pdfs/
COPY data/source_pdf_index.json ./data/source_pdf_index.json
COPY frontend/dist/ ./frontend/dist/

# Vertex-only intelligence (never AI Studio). Other config is injected by Cloud
# Run env vars; ADC supplies credentials via the Cloud Run service account.
ENV GOOGLE_GENAI_USE_VERTEXAI=true \
    PYTHONUNBUFFERED=1

# Cloud Run provides $PORT (8080). Bind it; default for local `docker run`.
CMD exec uvicorn noticeflow.api:app --host 0.0.0.0 --port ${PORT:-8080}

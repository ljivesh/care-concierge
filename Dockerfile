# ---- Stage 1: build the React frontend into static files ----
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the Python app, which also serves the built frontend ----
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model's weights into the image (about 1 GB), so the app and
# `make eval` never download anything at run time. Kept outside /app because
# compose mounts the source code over /app during development.
ENV FASTEMBED_CACHE_PATH=/opt/models
COPY app/__init__.py app/embeddings.py app/
RUN python -m app.embeddings

# The built page. Outside /app for the same reason as the model weights.
COPY --from=frontend /frontend/dist /opt/frontend

COPY . .

EXPOSE 8000
# Migrate, seed, ingest the corpus, then serve. The first three are safe to repeat.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && python -m app.ingest && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

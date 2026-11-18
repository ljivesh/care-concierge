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

COPY . .

EXPOSE 8000
# Migrate, seed, ingest the corpus, then serve. The first three are safe to repeat.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && python -m app.ingest && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

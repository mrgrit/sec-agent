FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir \
      fastapi==0.115.6 uvicorn[standard]==0.34.0 \
      sqlalchemy==2.0.36 psycopg2-binary==2.9.10 \
      pydantic==2.10.4 pydantic-settings==2.7.1 \
      redis==5.2.1 rq==2.1.0 \
      paramiko==3.5.0 \
      python-multipart==0.0.20 \
      cryptography==44.0.0 \
      httpx==0.27.2

COPY app /app/app

CMD ["bash", "-lc", "python -m app.main"]

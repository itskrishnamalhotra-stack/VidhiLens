FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LEGALAI_DATABASE_PATH=/data/legalai.sqlite \
    LEGALAI_CATALOGUE_PATH=/artifacts/rag_catalogue_v1.json

WORKDIR /opt/legalai
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY exports/rag_catalogue_v1.json /artifacts/rag_catalogue_v1.json
RUN mkdir -p /data && useradd --create-home --uid 10001 legalai && chown -R legalai:legalai /data
USER legalai

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers"]


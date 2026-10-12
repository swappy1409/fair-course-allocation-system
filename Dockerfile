# One container: builds the React frontend, then serves it and the API from FastAPI.
FROM node:22-alpine AS web
WORKDIR /web
COPY app/web/package.json app/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FCA_DATA_DIR=/data
WORKDIR /srv/app
COPY requirements.txt /srv/
RUN pip install --no-cache-dir -r /srv/requirements.txt
COPY app/fca ./fca
COPY app/config ./config
COPY app/data ./data
COPY --from=web /web/dist ./web/dist
RUN useradd --create-home fca && mkdir /data && chown fca /data
USER fca
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# One worker on purpose: sign-in attempt counting and the solver cache live in this process.
CMD ["uvicorn", "fca.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

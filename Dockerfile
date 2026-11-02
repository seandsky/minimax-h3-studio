FROM node:22-bookworm-slim AS web
WORKDIR /build
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements-macos.txt ./
RUN pip install --no-cache-dir -r requirements-macos.txt
COPY server/ ./server/
COPY --from=web /build/dist ./web_dist/
ENV H3_HOST=0.0.0.0 H3_PORT=8000 H3_DATA=/data H3_WORKFLOWS=/workflows H3_WEB_DIST=/app/web_dist PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1
CMD ["python", "server/app.py"]

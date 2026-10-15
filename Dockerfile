# Stage 1: build the React front end
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: Python server (API + the built front end)
FROM python:3.14-slim
# chromium = PDF export of the situation report (headless print); fonts-noto-core = Devanagari (Nepali) glyphs
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist /app/web/dist
# Render sets $PORT; default 8000 elsewhere. The app lists finished runs found in $FLOODSYS_OUT.
# Public demo: finished runs only (a free instance cannot run an analysis). Set BEACONSPACE_ANALYZE=on (and a BEACONSPACE_TOKEN) to allow runs.
ENV FLOODSYS_OUT=/app/examples BEACONSPACE_ANALYZE=off
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.12-slim
# chromium = PDF export of the situation report (headless print); fonts-noto-core = Devanagari (Nepali) glyphs
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-noto-core && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Render sets $PORT; default 8501 elsewhere. The dashboard lists finished runs found in $FLOODSYS_OUT.
ENV FLOODSYS_OUT=/app/examples
EXPOSE 8501
CMD ["sh", "-c", "streamlit run app/dashboard.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true --browser.gatherUsageStats=false"]

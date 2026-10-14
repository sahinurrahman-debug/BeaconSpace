FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgdal-dev gdal-bin chromium && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app/dashboard.py", "--server.address=0.0.0.0"]

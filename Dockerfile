FROM python:3.12-slim

# chromium печатает PDF, шрифты нужны браузеру для отрисовки диаграмм
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    A2PDF_CHROME=/usr/bin/chromium \
    A2PDF_TMP=/tmp/a2pdf \
    A2PDF_OUT=/tmp/a2pdf-out \
    A2PDF_WORKERS=2

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2pdf ./a2pdf

# Шрифты и mermaid уже лежат в образе — сервис не ходит в интернет на старте.
RUN python -c "import a2pdf; a2pdf.ensure_assets()" \
    && mkdir -p /tmp/a2pdf /tmp/a2pdf-out

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=4)"

CMD ["uvicorn", "a2pdf.web:app", "--host", "0.0.0.0", "--port", "8000"]

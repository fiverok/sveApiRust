FROM python:3.11-slim

# Обновляем сертификаты и устанавливаем sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    sqlite3 \
    && update-ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем requirements.txt и устанавливаем зависимости с доверием к pypi.org
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    --trusted-host pypi.python.org

COPY app.py .
COPY static/ ./static/

RUN mkdir -p /data

EXPOSE 21114

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org

COPY app.py .
COPY static/ ./static/

RUN mkdir -p /data

EXPOSE 21114

ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]

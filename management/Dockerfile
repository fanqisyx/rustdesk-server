FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home manager
COPY app.py db.py models.py security.py ./
COPY static ./static
RUN mkdir /data && chown manager:manager /data
USER manager
ENV RDM_DATABASE=/data/management.sqlite3 PYTHONUNBUFFERED=1
EXPOSE 21114
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:21114/healthz', timeout=3)"
CMD ["python", "app.py", "serve", "--host", "0.0.0.0"]

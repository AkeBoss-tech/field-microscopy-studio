FROM python:3.11-slim
RUN useradd -m -u 1000 studio
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=studio:studio app ./app
COPY --chown=studio:studio starter ./starter
USER studio
ENV STUDIO_ROOT=/app STUDIO_STORE=/tmp/field-store STUDIO_BIND=0.0.0.0 STUDIO_DEMO=1 STUDIO_UPLOAD_MB=100 STUDIO_STORE_MB=1500 STUDIO_MAX_VOXELS=64000000
EXPOSE 7860
CMD ["python", "app/server.py", "--port", "7860"]

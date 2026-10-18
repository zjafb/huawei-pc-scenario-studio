FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 GRADIO_ANALYTICS_ENABLED=False PORT=7860
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY rules ./rules
COPY prompts ./prompts
COPY connectors.py run_records.py run.py ./
RUN useradd --create-home --uid 1000 appuser && mkdir -p /app/data/private /app/data/whitelist && chown -R appuser:appuser /app
USER appuser
EXPOSE 7860
CMD ["python", "run.py"]

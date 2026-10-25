FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY job_rag ./job_rag
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home app
COPY data/jobs.csv ./data/jobs.csv
USER app
EXPOSE 8000 8001
CMD ["job-rag", "serve", "--host", "0.0.0.0", "--port", "8000"]

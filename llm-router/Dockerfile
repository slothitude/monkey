FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY llm_router/ ./llm_router/
COPY config.yaml.example ./config.yaml.example

# Create directory for config and copy example as default
RUN mkdir -p /app/data && \
    cp ./config.yaml.example ./data/config.yaml

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/app/data/config.yaml

# Run the API server
CMD ["python", "-m", "llm_router.server.api", "/app/data/config.yaml"]

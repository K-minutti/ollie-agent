# Use Python 3.11 for better performance
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    tar \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Prometheus Promtool
ENV PROMETHEUS_VERSION=2.53.0
RUN wget https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz \
    && tar xvfz prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz \
    && cp prometheus-${PROMETHEUS_VERSION}.linux-amd64/promtool /usr/local/bin/promtool \
    && chmod +x /usr/local/bin/promtool \
    && rm -rf prometheus-${PROMETHEUS_VERSION}.linux-amd64*

# Verify installation
RUN promtool --version

# Set up Python environment
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app files
COPY app.py agent.py ./

# Expose Streamlit port (HF Spaces expects 7860)
EXPOSE 7860

# Health check
HEALTHCHECK CMD curl --fail http://localhost:7860/_stcore/health

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=7860", "--server.headless=true"]
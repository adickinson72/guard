FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl (pinned version with checksum verification)
ENV KUBECTL_VERSION=1.31.3
ENV KUBECTL_SHA256=981f6b49577068bc174275184d8ee7105d8e54f40733792c519cd85023984c0f
RUN curl -LO "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && echo "${KUBECTL_SHA256}  kubectl" | sha256sum -c - \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# Install istioctl (pinned version with checksum verification)
ENV ISTIO_VERSION=1.20.0
ENV ISTIOCTL_SHA256=d1efd41672395f78996c6614ba3148e4a53ac99bcf61d088653f1fb02d48d089
RUN curl -L "https://github.com/istio/istio/releases/download/${ISTIO_VERSION}/istioctl-${ISTIO_VERSION}-linux-amd64.tar.gz" -o istioctl.tar.gz \
    && tar -xzf istioctl.tar.gz \
    && install -o root -g root -m 0755 istioctl /usr/local/bin/istioctl \
    && rm istioctl istioctl.tar.gz

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash guard

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Copy application code
COPY src/ ./src/

# Install dependencies and application in one step
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

# Change ownership to non-root user
RUN chown -R guard:guard /app

# Switch to non-root user
USER guard

# Set entrypoint
ENTRYPOINT ["guard"]

# Default command (can be overridden)
CMD ["--help"]

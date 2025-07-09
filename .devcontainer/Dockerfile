FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    build-essential \
    libpq-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (for potential frontend development)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# Create workspace directory
WORKDIR /workspace

# Copy requirements and install Python dependencies
COPY requirements.txt /workspace/
COPY python/packages/agent_fusion/pyproject.toml /workspace/python/packages/agent_fusion/
COPY python/packages/agent_fusion/opentelemetry_requirements.txt /workspace/python/packages/agent_fusion/

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt
RUN pip install -r python/packages/agent_fusion/opentelemetry_requirements.txt

# Install development tools
RUN pip install \
    black \
    flake8 \
    pytest \
    pytest-cov \
    mypy \
    pre-commit \
    ipython \
    jupyter

# Install the local packages in development mode
RUN pip install -e python/packages/agent_fusion/
RUN pip install -e python/packages/agent_fusion_agent/

# Set up git (for development)
RUN git config --global --add safe.directory /workspace

# Create a non-root user for development
RUN useradd -m -s /bin/bash devuser
RUN usermod -aG sudo devuser

# Switch to the development user
USER devuser

# Set the default command
CMD ["sleep", "infinity"] 
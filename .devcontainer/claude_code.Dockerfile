FROM ubuntu:24.04

# Install required dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code using official installer
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && cp $(readlink -f /root/.local/bin/claude) /usr/local/bin/claude \
    && chmod 755 /usr/local/bin/claude

# Create workspace directory with open permissions
RUN mkdir -p /workspace && chmod 777 /workspace

# Set working directory
WORKDIR /workspace

# Default command (runs as any user via --user flag)
CMD ["claude"]

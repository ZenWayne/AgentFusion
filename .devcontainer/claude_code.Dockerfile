FROM node:20-slim

# Install required dependencies for Claude Code
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# Create symlink for claude-code binary
RUN ln -s /usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js /usr/local/bin/claude-code

# Create non-root user
RUN useradd -m -u 1001 claude && \
    mkdir -p /workspace && \
    chown -R claude:claude /workspace /home/claude

# Set working directory
WORKDIR /workspace

# Switch to non-root user
USER claude

# Default command
CMD ["claude-code", "--dangerously-skip-permissions"]

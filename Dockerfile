FROM python:3.12-slim

# Install system dependencies + Node.js (required for opencode)
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user matching the host user
# uid=1000 gid=1000 matches web_wanderer on the host machine
# Files written to mounted volumes will be owned by you, not root
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g 1000 -m -s /bin/bash appuser

# Install opencode globally via npm as root so it's on PATH for all users
RUN npm install -g opencode-ai

WORKDIR /app

# Install Python dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Switch to non-root user for everything that runs
USER appuser

# Copy project code in
COPY --chown=appuser:appuser . .

# Default command — stays alive so you can exec into it
CMD ["tail", "-f", "/dev/null"]

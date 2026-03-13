FROM python:3.12-slim

# System deps + Node.js 22 for Claude CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Claude CLI (pin version for reproducibility)
RUN npm install -g @anthropic-ai/claude-code@2.1.74

WORKDIR /app

# Python deps (cached layer -- copy requirements first)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY pyproject.toml .
COPY src/ ./src/
COPY templates/ ./templates/

# Non-root user (required: Claude CLI refuses --dangerously-skip-permissions as root)
RUN useradd -m -s /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the entire workspace
COPY . .

# Install uv and dependencies
RUN pip install --no-cache-dir uv
RUN uv sync --frozen --no-dev --all-packages --directory .
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables for test agent
ENV LIVEKIT_URL=ws://livekit:7880
ENV LIVEKIT_API_KEY=devkey
ENV LIVEKIT_API_SECRET=secret
ENV LKSCALER_NAMESPACE=livekit-lkscaler
ENV LKSCALER_RESERVATION_TTL_SEC=30
ENV LKSCALER_ZK_SESSION_TIMEOUT_SEC=10
ENV LKSCALER_SYNC_INTERVAL_MS=250

# Default command - will be overridden per service
CMD ["python", "-m", "livekit.agents.cli", "start", "--debug"]

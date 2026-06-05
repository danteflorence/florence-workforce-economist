# Florence Workforce Economist — internal Streamlit app
# Self-hosted container image (Render / Railway / Fly / any container host).
# Python 3.11 (the app's code is compatible; this matches modern Streamlit Cloud).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- Dependencies (own layer so code edits don't reinstall everything) ---
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Application code + committed reference data ---
COPY . .

# A persistent disk mounts at /app/data at runtime and would shadow the
# committed reference data baked into the image. Move the baked data aside to
# /app/data_seed; the entrypoint copies it into /app/data on every boot, so:
#   • read-only reference data is always refreshed from the latest deploy
#   • mutable runtime state already on the disk (auth users/sessions, CRM
#     overrides, mail log, activations, activity log) is PRESERVED across deploys
RUN mv /app/data /app/data_seed && mkdir -p /app/data \
    && chmod +x /app/docker-entrypoint.sh

ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Render/Railway inject $PORT; default to 8501 for local `docker run`.
EXPOSE 8501
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Thai TikTok Studio — container (Hugging Face Spaces, Railway, any Docker host).
# Required secret/env: TTS_STUDIO_PASSWORD.  Port 7860 (Hugging Face default).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-color-emoji curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH \
    TTS_STUDIO_SERVER=1 TTS_STUDIO_HOST=0.0.0.0 TTS_STUDIO_PORT=7860 TTS_STUDIO_HOME=/home/user/ThaiTikTokStudio
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
RUN curl -fsSL https://claude.ai/install.sh | bash || true
COPY --chown=user . .

EXPOSE 7860
CMD ["python", "-m", "studio.app"]

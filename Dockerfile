FROM python:3.12-slim

# ---------------------------------------------------------------------------
# Sistem bağımlılıkları:
#   - ffmpeg      : ses akışı
#   - libopus0    : Discord ses kodlaması (Opus)
#   - nodejs      : bgutil POT sunucusu
#   - canvas için : cairo, pango, jpeg, gif, rsvg + derleme araçları
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    libopus-dev \
    curl \
    ca-certificates \
    build-essential \
    pkg-config \
    libcairo2-dev \
    libpango1.0-dev \
    libjpeg-dev \
    libgif-dev \
    librsvg2-dev \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------------------------------------------------------------------------
# Python bağımlılıkları
# ---------------------------------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# bgutil POT sunucusu bağımlılıkları
# ---------------------------------------------------------------------------
COPY bgutil-ytdlp-pot-provider/ ./bgutil-ytdlp-pot-provider/
RUN cd bgutil-ytdlp-pot-provider/server && npm install --omit=dev

# ---------------------------------------------------------------------------
# Uygulama dosyaları
# ---------------------------------------------------------------------------
COPY . .

RUN chmod +x start.sh

CMD ["bash", "start.sh"]

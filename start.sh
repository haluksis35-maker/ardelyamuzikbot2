#!/bin/bash
echo "=== BAŞLATMA LOGu ==="
echo "Çalışma dizini: $(pwd)"
echo "Node: $(node --version 2>&1 || echo 'YOK')"
echo "ffmpeg: $(which ffmpeg 2>&1 || echo 'YOK')"
echo "libopus: $(ls /usr/lib/*/libopus.so* 2>/dev/null || echo 'YOK')"

# bgutil POT sunucusunu arka planda başlat
echo ""
echo "bgutil POT sunucusu başlatılıyor..."
BGUTIL_PATH="/app/bgutil-ytdlp-pot-provider/server/build/main.js"

if [ -f "$BGUTIL_PATH" ]; then
    node "$BGUTIL_PATH" &
    BGUTIL_PID=$!
    echo "bgutil PID: $BGUTIL_PID, 5 saniye bekleniyor..."
    sleep 5
    if kill -0 "$BGUTIL_PID" 2>/dev/null; then
        echo "✅ bgutil sunucusu çalışıyor (PID: $BGUTIL_PID)"
        export GETPOT_BGUTIL_BASEURL=http://127.0.0.1:4416
    else
        echo "⚠️ bgutil sunucusu ÇÖKTÜ — loglara bak"
    fi
else
    echo "⚠️ bgutil bulunamadı: $BGUTIL_PATH"
fi

echo ""
echo "Discord botu başlatılıyor..."
exec python bot.py

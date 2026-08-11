#!/bin/bash
echo "=== BAŞLATMA LOGu ==="
echo "Çalışma dizini: $(pwd)"
echo "Node versiyon: $(node --version 2>&1 || echo 'Node bulunamadı')"
echo "ffmpeg yolu: $(which ffmpeg 2>&1 || echo 'ffmpeg bulunamadı')"

# bgutil POT sunucusunu arka planda başlat
echo ""
echo "bgutil POT sunucusu başlatılıyor..."

# Railway'de /app/ dizini kullanılır
BGUTIL_PATH="/app/bgutil-ytdlp-pot-provider/server/build/main.js"
if [ ! -f "$BGUTIL_PATH" ]; then
    echo "⚠️ bgutil dosyası bulunamadı: $BGUTIL_PATH"
    echo "Mevcut dosyalar:"
    ls -la /app/ 2>&1 | head -10
else
    node "$BGUTIL_PATH" &
    BGUTIL_PID=$!
    echo "bgutil PID: $BGUTIL_PID, 4 saniye bekleniyor..."
    sleep 4
    
    # Sunucu çalışıyor mu kontrol et
    if kill -0 "$BGUTIL_PID" 2>/dev/null; then
        echo "✅ bgutil sunucusu çalışıyor (PID: $BGUTIL_PID)"
        export GETPOT_BGUTIL_BASEURL=http://localhost:4416
    else
        echo "⚠️ bgutil sunucusu başlamadı — po_token olmadan devam ediliyor"
    fi
fi

echo ""
echo "Discord botu başlatılıyor..."
exec python bot.py

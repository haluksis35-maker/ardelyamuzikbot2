#!/bin/bash
echo "=== BAŞLATMA LOGu ==="
echo "Çalışma dizini: $(pwd)"
echo "Node versiyon: $(node --version 2>&1 || echo 'Node bulunamadı')"

# ffmpeg'i bul ve PATH + ortam değişkenine ekle
FFMPEG_BIN="$(which ffmpeg 2>/dev/null)"
if [ -z "$FFMPEG_BIN" ]; then
    echo "ffmpeg PATH'te yok, /nix/store içinde aranıyor..."
    FFMPEG_BIN="$(find /nix/store -maxdepth 4 -name ffmpeg -type f 2>/dev/null | head -1)"
    if [ -z "$FFMPEG_BIN" ]; then
        FFMPEG_BIN="$(find / -maxdepth 6 -name ffmpeg -type f 2>/dev/null | head -1)"
    fi
fi
if [ -n "$FFMPEG_BIN" ]; then
    echo "✅ ffmpeg bulundu: $FFMPEG_BIN"
    export FFMPEG_LOCATION="$FFMPEG_BIN"
    export PATH="$(dirname "$FFMPEG_BIN"):$PATH"
else
    echo "⚠️ ffmpeg HİÇBİR YERDE bulunamadı!"
fi

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

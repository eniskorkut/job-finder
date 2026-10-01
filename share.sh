#!/bin/bash
# Job Hunter Cloudflare Paylaşım Scripti

cd "$(dirname "$0")"

# 1. Port 5050 dinlenmiyorsa Python sunucusunu başlat
if ! lsof -i :5050 > /dev/null 2>&1; then
    echo "Port 5050 yerel sunucusu başlatılıyor..."
    python3 -m http.server 5050 > /dev/null 2>&1 &
    sleep 1
fi

echo "=========================================================="
echo " Cloudflare Tüneli Başlatılıyor..."
echo " Çıkan https://*.trycloudflare.com linkini arkadaşlarınızla paylaşabilirsiniz."
echo " Durdurmak için Ctrl + C tuşlarına basın."
echo "=========================================================="

./cloudflared tunnel --url http://localhost:5050

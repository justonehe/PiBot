#!/bin/bash
# run_dashboard.sh
# 强力启动 Dashboard Kiosk

export DISPLAY=:0
# 1. Kill old
pkill chromium || true
pkill chromium-browse || true
sleep 2

# 2. Detect Browser
if command -v chromium-browser &> /dev/null; then
    BROWSER="chromium-browser"
    ARGS="--kiosk --noerrdialogs --disable-infobars --check-for-update-interval=31536000"
elif command -v chromium &> /dev/null; then
    BROWSER="chromium"
    ARGS="--kiosk --noerrdialogs --disable-infobars --check-for-update-interval=31536000"
elif command -v firefox-esr &> /dev/null; then
    BROWSER="firefox-esr"
    ARGS="--kiosk"
else
    echo "No suitable browser found!"
    exit 1
fi

# 3. Start
setsid $BROWSER $ARGS http://localhost:5000 > dashboard.log 2>&1 < /dev/null &

sleep 3
if pgrep -f "$BROWSER" > /dev/null; then
    echo "SUCCESS: Dashboard Kiosk is running."
else
    echo "ERROR: Dashboard failed to start."
fi

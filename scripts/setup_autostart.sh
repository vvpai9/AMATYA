#!/usr/bin/env bash
# Enable JARVIS to launch on macOS login and wake
set -e

PLIST_SRC="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/com.jarvis.mac.plist"
DEST="$HOME/Library/LaunchAgents/com.jarvis.mac.plist"

mkdir -p "$HOME/Library/LaunchAgents"

if [ "$1" == "--disable" ]; then
    echo "Disabling JARVIS autostart..."
    launchctl unload "$DEST" 2>/dev/null || true
    rm -f "$DEST"
    echo "✅ Autostart disabled."
    exit 0
fi

echo "Enabling JARVIS autostart on user login and wake..."
cp "$PLIST_SRC" "$DEST"
launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"
echo "✅ JARVIS autostart enabled successfully in ~/Library/LaunchAgents/com.jarvis.mac.plist"

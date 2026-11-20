#!/usr/bin/env bash
# macOS Application Bundle (.app) & DMG Installer Builder for JARVIS Mark-LVII
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

BUILD_DIR="$DIR/build"
APP_DIR="$BUILD_DIR/Jarvis.app"
DMG_ROOT="$BUILD_DIR/dmg_root"
OUTPUT_DMG="$HOME/Desktop/Jarvis-Mark-LVII.dmg"

echo "=========================================="
echo "📦 Building JARVIS macOS App & DMG Installer"
echo "=========================================="

rm -rf "$BUILD_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"
mkdir -p "$DMG_ROOT"

# Copy Icon
if [ -f "$DIR/config/AppIcon.icns" ]; then
    cp "$DIR/config/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
fi

# Create Info.plist with proper Icon and metadata
cat <<EOF > "$APP_DIR/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Jarvis</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>com.fatihmakes.jarvis</string>
    <key>CFBundleName</key>
    <string>JARVIS</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>57.0</string>
    <key>CFBundleVersion</key>
    <string>57.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>JARVIS needs microphone access for voice control and live speech processing.</string>
    <key>NSCameraUsageDescription</key>
    <string>JARVIS needs camera access for visual perception and image analysis.</string>
</dict>
</plist>
EOF

# Create Launcher executable inside Contents/MacOS/Jarvis
cat <<'EOF' > "$APP_DIR/Contents/MacOS/Jarvis"
#!/usr/bin/env bash
REPO_DIR="$HOME/Downloads/Jarvise"

if [ ! -d "$REPO_DIR" ]; then
    REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../../../.." && pwd )"
fi

cd "$REPO_DIR"
LOG_FILE="$HOME/.jarvis_app.log"
echo "=== JARVIS Launch $(date) ===" >> "$LOG_FILE"

if [ -f "$REPO_DIR/.venv/bin/python" ]; then
    exec "$REPO_DIR/.venv/bin/python" main.py >> "$LOG_FILE" 2>&1
else
    exec python3 main.py >> "$LOG_FILE" 2>&1
fi
EOF

chmod +x "$APP_DIR/Contents/MacOS/Jarvis"
xattr -cr "$APP_DIR" 2>/dev/null || true

# Install directly to /Applications so there is only one official app bundle
echo "📲 Updating /Applications/Jarvis.app..."
rm -rf "/Applications/Jarvis.app"
cp -R "$APP_DIR" "/Applications/Jarvis.app"
xattr -cr "/Applications/Jarvis.app" 2>/dev/null || true

# Copy App to DMG root
cp -R "$APP_DIR" "$DMG_ROOT/"

# Create symlink to /Applications inside DMG for drag-and-drop install
ln -s /Applications "$DMG_ROOT/Applications"

echo "💿 Creating DMG Disk Image at: $OUTPUT_DMG..."
rm -f "$OUTPUT_DMG"
hdiutil create -volname "JARVIS Mark-LVII" -srcfolder "$DMG_ROOT" -ov -format UDZO "$OUTPUT_DMG"

# Eject any transient mounted volumes from creation
hdiutil info | grep "/Volumes/JARVIS" | awk '{print $1}' | while read -r dev; do
    hdiutil detach "$dev" -force 2>/dev/null || true
done

# Clean up build directory so macOS Spotlight does not index temporary build duplicates
echo "🧹 Cleaning up intermediate build directory to prevent duplicate Spotlight entries..."
rm -rf "$BUILD_DIR"

echo "✅ Official JARVIS App installed to /Applications/Jarvis.app"
echo "✅ DMG Installer ready at: $OUTPUT_DMG"

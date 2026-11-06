#!/bin/bash
# Build dist/memguard-<version>.dmg with "Install memguard.app" and "Uninstall memguard.app".
# The payload is `git archive HEAD`, i.e. exactly the committed files.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$REPO/pyproject.toml")"
STAGE="$(mktemp -d)/memguard"
mkdir -p "$STAGE" "$REPO/dist"

make_app() {  # name script
    local app="$STAGE/$1.app"
    mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources/payload"
    cp "$REPO/packaging/$2" "$app/Contents/MacOS/run"
    chmod +x "$app/Contents/MacOS/run"
    git -C "$REPO" archive HEAD | tar -x -C "$app/Contents/Resources/payload"
    cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$1</string>
  <key>CFBundleIdentifier</key><string>com.memguard.$2</string>
  <key>CFBundleExecutable</key><string>run</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
    plutil -lint "$app/Contents/Info.plist" >/dev/null
}
make_app "Install memguard" installer.sh
make_app "Uninstall memguard" uninstaller.sh
cp "$REPO/README.md" "$STAGE/README.md"
cp "$REPO/LICENSE" "$STAGE/LICENSE.txt"

OUT="$REPO/dist/memguard-$VERSION.dmg"
rm -f "$OUT"
hdiutil create -quiet -volname "memguard $VERSION" -srcfolder "$STAGE" -format UDZO "$OUT"
echo "$OUT"

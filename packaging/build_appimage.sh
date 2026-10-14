#!/usr/bin/env bash
# Packs dist/ELI (the PyInstaller build) into dist/ELI-<version>-x86_64.AppImage.
# usage: packaging/build_appimage.sh <version>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?usage: $0 <version>}"
APPDIR="$ROOT/build/ELI.AppDir"
[ -x "$ROOT/dist/ELI/ELI" ] || { echo "dist/ELI is missing: run pyinstaller packaging/eli.spec first" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr"
cp -a "$ROOT/dist/ELI" "$APPDIR/usr/app"
cp "$ROOT/LICENSE" "$APPDIR/LICENSE"
cp "$ROOT/packaging/eli.png" "$APPDIR/eli.png"
ln -s eli.png "$APPDIR/.DirIcon"

cat > "$APPDIR/eli.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=ELI
Comment=Local AI assistant
Exec=ELI
Icon=eli
Categories=Utility;
Terminal=false
EOF

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/app/ELI" "$@"
EOF
chmod +x "$APPDIR/AppRun"

TOOL="$ROOT/build/appimagetool"
if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$ROOT/dist/ELI-$VERSION-x86_64.AppImage"

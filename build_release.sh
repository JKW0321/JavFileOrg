#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSION="$("$PYTHON_BIN" -c 'from app_metadata import BASELINE_VERSION; print(BASELINE_VERSION)')"
VERSION_NUM="${VERSION#v}"
APP_NAME="JAVFileOrganizer-${VERSION}"
BUILD_DIR="build_release_${VERSION}"
DIST_DIR="dist_release_${VERSION}"
SPEC_PATH="${BUILD_DIR}/${APP_NAME}.spec"
ICON_PATH="assets/icons/JAVFileOrganizer.icns"
ICON_ABS_PATH="${ROOT_DIR}/${ICON_PATH}"
DESKTOP_APP="${HOME}/Desktop/${APP_NAME}.app"

if ! "$PYTHON_BIN" -c '
import webview
assert callable(getattr(webview, "create_window", None))
if __import__("sys").platform == "darwin":
    import objc, Cocoa, Quartz, WebKit, Security, UniformTypeIdentifiers
' >/dev/null 2>&1; then
  echo "Missing desktop component runtime. Install requirements.txt in the selected Python environment before building." >&2
  exit 1
fi

if [[ ! -f "$ICON_ABS_PATH" ]]; then
  echo "Missing icon: $ICON_ABS_PATH" >&2
  exit 1
fi

mkdir -p "$BUILD_DIR"
cat > "$SPEC_PATH" <<SPEC
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas = []
binaries = []
hiddenimports = [
    'app_metadata',
    'atomic_processor_v11',
    'download_service',
    'filename_rule_library',
    'filename_utils',
    'inspection_service',
    'jfo_icon_resources',
    'manifest_utils',
    'provider_router',
    'selenium_cookie_helper',
    'selenium_javlibrary',
    'webview_app',
    'workflow_service',
]

datas += [('${ROOT_DIR}/webui', 'webui')]
datas += collect_data_files('certifi')
datas += collect_data_files('webdriver_manager')
hiddenimports += collect_submodules('providers')
hiddenimports += collect_submodules('selenium')
hiddenimports += collect_submodules('webdriver_manager')
hiddenimports += collect_submodules('webview')

tmp_ret = collect_all('webview')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_ret = collect_all('PIL')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['${ROOT_DIR}/webview_app.py'],
    pathex=['${ROOT_DIR}'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='${APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='${APP_NAME}',
)
app = BUNDLE(
    coll,
    name='${APP_NAME}.app',
    icon='${ICON_ABS_PATH}',
    bundle_identifier='com.javfileorganizer.app',
    info_plist={
        'CFBundleShortVersionString': '${VERSION_NUM}',
        'CFBundleVersion': '${VERSION_NUM}',
    },
)
SPEC

"$PYTHON_BIN" -m PyInstaller --clean --noconfirm \
  --distpath "$DIST_DIR" \
  --workpath "$BUILD_DIR/work" \
  "$SPEC_PATH"

APP_PATH="${DIST_DIR}/${APP_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Build did not create $APP_PATH" >&2
  exit 1
fi

CERTIFI_BUNDLE="$APP_PATH/Contents/Frameworks/certifi/cacert.pem"
if [[ ! -f "$CERTIFI_BUNDLE" ]]; then
  echo "Build is missing the TLS certificate bundle: $CERTIFI_BUNDLE" >&2
  exit 1
fi

xattr -cr "$APP_PATH" || true
find "$APP_PATH" -name Python.framework -exec xattr -d com.apple.FinderInfo {} \; 2>/dev/null || true
find "$APP_PATH" -name Python.framework -exec xattr -d 'com.apple.fileprovider.fpfs#P' {} \; 2>/dev/null || true
find "$APP_PATH" -name Python.framework -exec xattr -d com.apple.provenance {} \; 2>/dev/null || true
find "$APP_PATH" -name Python.framework -exec xattr -d -s com.apple.FinderInfo {} \; 2>/dev/null || true
find "$APP_PATH" -name Python.framework -exec xattr -d -s 'com.apple.fileprovider.fpfs#P' {} \; 2>/dev/null || true
find "$APP_PATH" -name Python.framework -exec xattr -d -s com.apple.provenance {} \; 2>/dev/null || true
for framework_path in \
  "$APP_PATH/Contents/Frameworks/Python.framework" \
  "$APP_PATH/Contents/Resources/Python.framework"
do
  if [[ -e "$framework_path" || -L "$framework_path" ]]; then
    xattr -d com.apple.FinderInfo "$framework_path" 2>/dev/null || true
    xattr -d 'com.apple.fileprovider.fpfs#P' "$framework_path" 2>/dev/null || true
    xattr -d com.apple.provenance "$framework_path" 2>/dev/null || true
    xattr -d -s com.apple.FinderInfo "$framework_path" 2>/dev/null || true
    xattr -d -s 'com.apple.fileprovider.fpfs#P' "$framework_path" 2>/dev/null || true
    xattr -d -s com.apple.provenance "$framework_path" 2>/dev/null || true
  fi
done
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

case "$DESKTOP_APP" in
  "$HOME"/Desktop/JAVFileOrganizer-v*.app) ;;
  *)
    echo "Refusing to replace unexpected desktop path: $DESKTOP_APP" >&2
    exit 1
    ;;
esac
DESKTOP_EXECUTABLE="$DESKTOP_APP/Contents/MacOS/$APP_NAME"
if pgrep -f "$DESKTOP_EXECUTABLE" >/dev/null 2>&1; then
  echo "JAVFileOrganizer is still running. Close it before replacing the desktop app." >&2
  exit 1
fi
rm -rf "$DESKTOP_APP"
ditto --noextattr --norsrc "$APP_PATH" "$DESKTOP_APP"
codesign --force --deep --sign - "$DESKTOP_APP"
codesign --verify --deep --strict --verbose=2 "$DESKTOP_APP"

echo "$DESKTOP_APP"

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
    'jfo_icon_resources',
    'manifest_utils',
    'provider_router',
    'selenium_cookie_helper',
    'selenium_javlibrary',
    'workflow_service',
]

datas += collect_data_files('webdriver_manager')
hiddenimports += collect_submodules('providers')
hiddenimports += collect_submodules('selenium')
hiddenimports += collect_submodules('webdriver_manager')

tmp_ret = collect_all('PIL')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['${ROOT_DIR}/jav_file_organizer.py'],
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

xattr -cr "$APP_PATH" || true
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"

case "$DESKTOP_APP" in
  "$HOME"/Desktop/JAVFileOrganizer-v*.app) ;;
  *)
    echo "Refusing to replace unexpected desktop path: $DESKTOP_APP" >&2
    exit 1
    ;;
esac
rm -rf "$DESKTOP_APP"
ditto --noextattr --norsrc "$APP_PATH" "$DESKTOP_APP"
codesign --force --deep --sign - "$DESKTOP_APP"
codesign --verify --deep --strict --verbose=2 "$DESKTOP_APP"

echo "$DESKTOP_APP"

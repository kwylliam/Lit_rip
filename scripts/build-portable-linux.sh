#!/bin/sh
# Build a self-contained Linux folder and an archive that preserves permissions.
set -eu

lit_rip_script=$(readlink -f -- "$0")
lit_rip_root=$(dirname -- "$(dirname -- "$lit_rip_script")")

# Build against the host libraries, even when run from a Flatpak editor.
if [ -f /.flatpak-info ]; then
    exec flatpak-spawn --host "$lit_rip_script" "$@"
fi

cd -- "$lit_rip_root"
if [ -n "${LIT_RIP_PYTHON:-}" ]; then
    lit_rip_python=$LIT_RIP_PYTHON
    if [ ! -x "$lit_rip_python" ]; then
        printf 'Configured Python build environment is missing: %s\n' "$lit_rip_python" >&2
        exit 1
    fi
else
    for lit_rip_candidate in \
        "$lit_rip_root/.venv/bin/python" \
        "$lit_rip_root/.venv-desktop/bin/python"; do
        if [ -x "$lit_rip_candidate" ] && \
            "$lit_rip_candidate" -m PyInstaller --version >/dev/null 2>&1; then
            lit_rip_python=$lit_rip_candidate
            break
        fi
    done
fi
if [ -z "${lit_rip_python:-}" ]; then
    lit_rip_python="$lit_rip_root/.venv/bin/python"
fi
if [ ! -x "$lit_rip_python" ]; then
    printf 'Missing Python build environment: %s\n' "$lit_rip_python" >&2
    exit 1
fi
if ! "$lit_rip_python" -m PyInstaller --version >/dev/null 2>&1; then
    printf 'Install PyInstaller first: %s -m pip install "pyinstaller>=6,<7"\n' "$lit_rip_python" >&2
    exit 1
fi

lit_rip_version=$("$lit_rip_python" -m lit_rip --version | cut -d " " -f 2)
lit_rip_release="lit-rip-linux-x86_64-v$lit_rip_version"
lit_rip_folder="$lit_rip_root/dist/$lit_rip_release"
lit_rip_archive="$lit_rip_root/dist/$lit_rip_release.tar.gz"
if [ -e "$lit_rip_folder" ] || [ -e "$lit_rip_archive" ]; then
    printf 'Build output already exists. Move it before rebuilding: %s\n' "$lit_rip_folder" >&2
    exit 1
fi
mkdir -p "$lit_rip_folder/app" "$lit_rip_root/build/portable-work"

"$lit_rip_python" -m PyInstaller \
    --noconfirm --clean --onedir --name lit-rip \
    --collect-all fanficfare --collect-all lit_rip \
    --distpath "$lit_rip_folder/app" \
    --workpath "$lit_rip_root/build/portable-work" \
    --specpath "$lit_rip_root/build" \
    "$lit_rip_root/scripts/frozen_entry.py"

cp "$lit_rip_root/launch-lit-rip.sh" "$lit_rip_folder/launch-lit-rip.sh"
cp "$lit_rip_root/PORTABLE.md" "$lit_rip_folder/PORTABLE.md"
: > "$lit_rip_folder/.portable-bundle"
"$lit_rip_folder/app/lit-rip/lit-rip" --version

tar -czf "$lit_rip_archive" -C "$lit_rip_root/dist" "$lit_rip_release"
printf 'Portable folder: %s\nArchive: %s\n' "$lit_rip_folder" "$lit_rip_archive"

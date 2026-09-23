#!/bin/sh
# Launch on the Linux desktop, even when called from a Flatpak editor.
set -eu

lit_rip_script=$(readlink -f -- "$0")
lit_rip_dir=$(dirname -- "$lit_rip_script")

if [ -f /.flatpak-info ]; then
    exec flatpak-spawn --host "$lit_rip_script" "$@"
fi

cd -- "$lit_rip_dir"

# A portable release includes its own interpreter and Python dependencies.
lit_rip_bundle="$lit_rip_dir/app/lit-rip/lit-rip"
if [ -f "$lit_rip_dir/.portable-bundle" ]; then
    if [ ! -x "$lit_rip_bundle" ]; then
        printf 'Lit Rip bundle is incomplete or not executable: %s\n' "$lit_rip_bundle" >&2
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --title="Lit Rip could not start" --text="The portable bundle is incomplete or not executable. Extract the whole archive to a local Linux folder." || true
        fi
        exit 1
    fi
    lit_rip_state="${XDG_STATE_HOME:-$HOME/.local/state}/lit-rip"
    mkdir -p "$lit_rip_state"
    exec "$lit_rip_bundle" gui "$@" >> "$lit_rip_state/launcher.log" 2>&1
fi

lit_rip_log="$lit_rip_dir/.lit-rip-launcher.log"
lit_rip_python="$lit_rip_dir/.venv-desktop/bin/python"
if [ ! -x "$lit_rip_python" ]; then
    lit_rip_python="$lit_rip_dir/.venv/bin/python"
fi

lit_rip_error() {
    printf '%s\n' "$1" >&2
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="Lit Rip could not start" --text="$1" || true
    fi
    exit 1
}

if [ ! -x "$lit_rip_python" ]; then
    lit_rip_error "The Python environment is missing. See the Linux Mint desktop launcher setup in $lit_rip_dir/README.md."
fi

# A Flatpak-created environment can exist yet be unusable on the host.
if ! "$lit_rip_python" -c 'import lit_rip.cli; import lit_rip.web' >> "$lit_rip_log" 2>&1; then
    lit_rip_error "The app's Python dependencies could not load. See the Linux Mint desktop launcher setup in $lit_rip_dir/README.md. Details are in $lit_rip_log."
fi

exec "$lit_rip_python" -m lit_rip gui "$@" >> "$lit_rip_log" 2>&1

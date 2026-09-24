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
lit_rip_python=""
for lit_rip_candidate in \
    "$lit_rip_dir/.venv/bin/python" \
    "$lit_rip_dir/.venv-desktop/bin/python"; do
    if [ -x "$lit_rip_candidate" ] && \
        "$lit_rip_candidate" -c 'import lit_rip.cli; import lit_rip.web' >/dev/null 2>&1; then
        lit_rip_python="$lit_rip_candidate"
        break
    fi
done

lit_rip_error() {
    printf '%s\n' "$1" >&2
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="Lit Rip could not start" --text="$1" || true
    fi
    exit 1
}

lit_rip_portable_hint() {
    find "$lit_rip_dir/dist" -maxdepth 1 -type f -name 'lit-rip-linux-x86_64-v*.tar.gz' -print 2>/dev/null | sort -V | tail -n 1
}

if [ -z "$lit_rip_python" ]; then
    lit_rip_portable_archive=$(lit_rip_portable_hint)
    if [ -n "$lit_rip_portable_archive" ]; then
        lit_rip_error "This is the source-checkout launcher, but its Python environment is missing. Extract the portable bundle at $lit_rip_portable_archive and run the launch-lit-rip.sh inside the extracted folder."
    fi
    lit_rip_error "The source checkout's Python environment is missing or its dependencies are not installed. Run: $lit_rip_dir/.venv/bin/python -m pip install -e $lit_rip_dir. Or run the portable bundle's launch-lit-rip.sh."
fi

# A Flatpak-created environment can exist yet be unusable on the host.
if ! "$lit_rip_python" -c 'import lit_rip.cli; import lit_rip.web' >> "$lit_rip_log" 2>&1; then
    lit_rip_portable_archive=$(lit_rip_portable_hint)
    if [ -n "$lit_rip_portable_archive" ]; then
        lit_rip_error "The source checkout's Python environment could not load. Extract the portable bundle at $lit_rip_portable_archive and run the launch-lit-rip.sh inside the extracted folder. Details are in $lit_rip_log."
    fi
    lit_rip_error "The app's Python dependencies could not load. See the source checkout setup in $lit_rip_dir/README.md. Details are in $lit_rip_log."
fi

exec "$lit_rip_python" -m lit_rip gui "$@" >> "$lit_rip_log" 2>&1

# Lit Rip portable Linux bundle

This folder contains the app, its Python runtime, and its Python dependencies. You do not need to install Python or packages on the destination computer.

Extract `lit-rip-linux-x86_64-v0.2.0.tar.gz` to a local Linux folder (the archive preserves executable permissions). Run `launch-lit-rip.sh` or use its full path as a desktop launcher's command. The browser app opens automatically. Keep the app running while you use it.

The folder can move without reinstalling or editing the script. Keep `app/` next to `launch-lit-rip.sh`; the binary and its `_internal/` folder must stay together. The app still needs an internet connection to search and download stories and a browser to display the interface.

This bundle was built for 64-bit Linux. It may fail on older distributions because Linux system libraries are not fully portable. For another architecture or older distribution, rebuild there using `scripts/build-portable-linux.sh` from the source project. A Windows or macOS version would need a separate build on that system.

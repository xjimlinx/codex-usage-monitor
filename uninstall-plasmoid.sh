#!/usr/bin/env bash
set -euo pipefail

kpackagetool6 --type Plasma/Applet --remove io.github.codexdesktoplinux.usagemonitor
echo "Uninstalled Plasma widget: Codex Usage"

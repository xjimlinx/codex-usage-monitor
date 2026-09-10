#!/usr/bin/env bash
set -euo pipefail

plugin_id="io.github.codexdesktoplinux.usagemonitor"
icon_path="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/$plugin_id.svg"

kpackagetool6 --type Plasma/Applet --remove "$plugin_id"
rm -f -- "$icon_path"
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null
echo "Uninstalled Plasma widget: Codex Usage"

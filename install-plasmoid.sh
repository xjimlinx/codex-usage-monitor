#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
package_dir="$script_dir/plasmoid"
plugin_id="io.github.codexdesktoplinux.usagemonitor"
icon_source="$package_dir/contents/icons/$plugin_id.svg"
icon_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

command -v kpackagetool6 >/dev/null || {
    echo "kpackagetool6 is required (Plasma 6)" >&2
    exit 1
}

install -d -m 0755 "$icon_dir"
install -m 0644 "$icon_source" "$icon_dir/$plugin_id.svg"

if kpackagetool6 --type Plasma/Applet --show "$plugin_id" >/dev/null 2>&1; then
    kpackagetool6 --type Plasma/Applet --upgrade "$package_dir"
else
    kpackagetool6 --type Plasma/Applet --install "$package_dir"
fi

command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null

echo "Installed Plasma widget: Codex Usage"
echo "Add it from: panel edit mode -> Add Widgets -> Codex Usage"

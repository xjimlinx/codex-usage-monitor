#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
package_dir="$script_dir/plasmoid"
plugin_id="io.github.codexdesktoplinux.usagemonitor"

command -v kpackagetool6 >/dev/null || {
    echo "kpackagetool6 is required (Plasma 6)" >&2
    exit 1
}

if kpackagetool6 --type Plasma/Applet --show "$plugin_id" >/dev/null 2>&1; then
    kpackagetool6 --type Plasma/Applet --upgrade "$package_dir"
else
    kpackagetool6 --type Plasma/Applet --install "$package_dir"
fi

echo "Installed Plasma widget: Codex Usage"
echo "Add it from: panel edit mode -> Add Widgets -> Codex Usage"

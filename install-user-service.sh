#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/codex-usage-monitor"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/codex-usage-monitor"
environment_file="$config_dir/environment"
unit_name="codex-usage-monitor.service"

command -v python3 >/dev/null || {
    echo "python3 is required" >&2
    exit 1
}
command -v codex >/dev/null || {
    echo "codex is required and must be available in PATH" >&2
    exit 1
}
command -v systemctl >/dev/null || {
    echo "systemctl is required" >&2
    exit 1
}

install -d -m 0755 "$install_dir" "$unit_dir"
install -d -m 0700 "$config_dir"
install -m 0755 "$script_dir/codex_usage_monitor.py" "$install_dir/codex_usage_monitor.py"

: >"$environment_file"
chmod 0600 "$environment_file"
for variable_name in http_proxy https_proxy all_proxy no_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY; do
    variable_value="${!variable_name-}"
    if [ -n "$variable_value" ]; then
        case "$variable_value" in
            *$'\n'*|*$'\r'*)
                echo "Ignoring invalid $variable_name containing a newline" >&2
                continue
                ;;
        esac
        variable_value="${variable_value//\\/\\\\}"
        variable_value="${variable_value//\"/\\\"}"
        printf '%s="%s"\n' "$variable_name" "$variable_value" >>"$environment_file"
    fi
done

sed "s#%h/.local/lib/codex-usage-monitor#$install_dir#g" \
    "$script_dir/$unit_name" >"$unit_dir/$unit_name"
chmod 0644 "$unit_dir/$unit_name"

systemctl --user daemon-reload
systemctl --user enable "$unit_name"
systemctl --user restart "$unit_name"

echo "Installed and started $unit_name"
echo "Dashboard: http://127.0.0.1:9000/"

#!/usr/bin/env bash
set -euo pipefail

install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/codex-usage-monitor"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/codex-usage-monitor"
unit_name="codex-usage-monitor.service"

systemctl --user disable --now "$unit_name" 2>/dev/null || true

if [ -f "$unit_dir/$unit_name" ]; then
    unlink "$unit_dir/$unit_name"
fi
if [ -f "$install_dir/codex_usage_monitor.py" ]; then
    unlink "$install_dir/codex_usage_monitor.py"
fi
if [ -d "$install_dir" ]; then
    rmdir "$install_dir" 2>/dev/null || true
fi
if [ -f "$config_dir/environment" ]; then
    unlink "$config_dir/environment"
fi
if [ -d "$config_dir" ]; then
    rmdir "$config_dir" 2>/dev/null || true
fi

systemctl --user daemon-reload
systemctl --user reset-failed "$unit_name" 2>/dev/null || true
echo "Uninstalled $unit_name"

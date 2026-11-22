#!/bin/bash
# Install the WebUI user services and app launcher for the current user.
# The service is started on demand by the launcher; to start it at login:
#   systemctl --user enable antelope-webui
set -e
repo=$(cd "$(dirname "$0")/.." && pwd)
unit_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
app_dir=${XDG_DATA_HOME:-$HOME/.local/share}/applications
mkdir -p "$unit_dir" "$app_dir"
sed "s|@REPO@|$repo|g" "$repo/packaging/antelope-webui.service" >"$unit_dir/antelope-webui.service"
sed "s|@REPO@|$repo|g" "$repo/packaging/antelope-webui@.service" >"$unit_dir/antelope-webui@.service"
sed "s|@REPO@|$repo|g" "$repo/packaging/antelope-webui.desktop" >"$app_dir/antelope-webui.desktop"
systemctl --user daemon-reload
echo "Installed. Launch 'Antelope Control' from the app menu."

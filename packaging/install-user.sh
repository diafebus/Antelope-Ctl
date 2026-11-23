#!/bin/bash
# Install the WebUI user services and app launcher for the current user.
# The service is started on demand by the launcher; to start it at login:
#   systemctl --user enable antelope-webui
set -e
repo=$(cd "$(dirname "$0")/.." && pwd)
unit_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
app_dir=${XDG_DATA_HOME:-$HOME/.local/share}/applications
mkdir -p "$unit_dir" "$app_dir"
python3 - "$repo" "$unit_dir" "$app_dir" <<'PYTHON'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
units = Path(sys.argv[2])
apps = Path(sys.argv[3])
packaging = repo / 'packaging'

# systemd expands percent specifiers in unit file commands.
systemd_path = str(repo).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
for name in ('antelope-webui.service', 'antelope-webui@.service'):
    template = (packaging / name).read_text(encoding='utf-8')
    (units / name).write_text(template.replace('@REPO@', systemd_path), encoding='utf-8')

# The desktop-entry string layer and its Exec arguments each escape backslashes.
desktop_path = str(repo).replace('\\', '\\\\')
exec_path = str(repo)
for character in ('\\', '"', '`', '$'):
    exec_path = exec_path.replace(character, '\\' + character)
exec_path = exec_path.replace('\\', '\\\\').replace('%', '%%')
name = 'antelope-webui.desktop'
template = (packaging / name).read_text(encoding='utf-8')
desktop = template.replace('@REPO@', desktop_path).replace('@REPO_EXEC@', exec_path)
(apps / name).write_text(desktop, encoding='utf-8')
PYTHON
systemctl --user daemon-reload
echo "Installed. Launch 'Antelope Control' from the app menu."

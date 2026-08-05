#!/usr/bin/env sh
set -eu

repository='https://github.com/ThisisPeggy/hermes-browser-connector'
plugin_name='hermes-browser'
hermes_home="${HERMES_HOME:-$HOME/.hermes}"
plugin_dir="$hermes_home/plugins/$plugin_name"
gateway_stopped=0

restart_gateway() {
  if [ "$gateway_stopped" -eq 1 ]; then
    hermes gateway restart || true
  fi
}
trap restart_gateway EXIT INT TERM

command -v hermes >/dev/null 2>&1 || { echo 'Hermes is not installed or is not on PATH.' >&2; exit 1; }
command -v git >/dev/null 2>&1 || { echo 'Git is not installed or is not on PATH.' >&2; exit 1; }

hermes gateway stop >/dev/null 2>&1 || true
gateway_stopped=1

if [ -d "$plugin_dir/.git" ]; then
  echo 'Updating Hermes Browser Connector...'
  git -C "$plugin_dir" fetch --prune origin
  git -C "$plugin_dir" checkout --force origin/main
  hermes plugins enable "$plugin_name" --no-allow-tool-override
else
  echo 'Installing Hermes Browser Connector...'
  hermes plugins install "$repository" --enable
fi

if command -v python3 >/dev/null 2>&1; then
  python3 "$plugin_dir/connect.py"
else
  python "$plugin_dir/connect.py"
fi

echo 'Hermes Browser Connector is ready.'

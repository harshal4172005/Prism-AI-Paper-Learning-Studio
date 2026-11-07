#!/bin/sh
set -eu
APP=/opt/prism-learning
if [ -e "$APP" ] && [ ! -f "$APP/.prism-owned" ]; then
  echo "Refusing to modify an existing unrelated directory" >&2
  exit 1
fi
if [ ! -d "$APP" ]; then
  sudo install -d -m 755 "$APP"
  sudo touch "$APP/.prism-owned"
fi
if ! id prism-learning >/dev/null 2>&1; then
  sudo useradd --system --home-dir /var/lib/prism-learning --shell /usr/sbin/nologin prism-learning
fi
sudo install -d -m 700 -o prism-learning -g prism-learning /var/lib/prism-learning
sudo tar -xzf "$1" -C "$APP"
sudo python3 -m venv "$APP/venv"
sudo "$APP/venv/bin/python" -m pip install --no-cache-dir --disable-pip-version-check -r "$APP/deploy/requirements-server.lock"
sudo chmod -R a+rX "$APP/app"
sudo install -m 644 "$APP/deploy/prism-learning.service" /etc/systemd/system/prism-learning.service
sudo systemctl daemon-reload
printf 'Isolated app prepared. Existing application directories were not changed.\n'

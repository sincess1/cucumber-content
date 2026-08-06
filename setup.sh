#!/usr/bin/env bash
set -euo pipefail

python3 -m venv venv
venv/bin/pip install -q -r requirements.txt

if ! fc-list 2>/dev/null | grep -qiE 'dejavu|liberation'; then
  APT="apt-get"
  command -v sudo >/dev/null 2>&1 && [ "$(id -u)" != "0" ] && APT="sudo apt-get"
  $APT update -qq && $APT install -y -qq fonts-dejavu-core fonts-liberation \
    || echo "warn: шрифты не поставились, баннер уйдёт на дефолтный"
fi

venv/bin/python -c "from PIL import Image; print('pillow ok')"

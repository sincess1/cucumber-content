#!/usr/bin/env bash
set -uo pipefail

pip install -q -r requirements.txt

if ! fc-list 2>/dev/null | grep -qiE 'dejavu|liberation'; then
  APT="apt-get"
  command -v sudo >/dev/null 2>&1 && [ "$(id -u)" != "0" ] && APT="sudo apt-get"
  $APT update -qq && $APT install -y -qq fonts-dejavu-core fonts-liberation \
    || echo "warn: шрифты не поставились, баннер уйдёт на дефолтный"
fi

python -c "from PIL import Image; print('pillow ok')"

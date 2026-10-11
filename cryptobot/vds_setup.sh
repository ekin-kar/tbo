#!/bin/bash
# TBO server install / update, run as root by tbo_servers.bat (Ubuntu 22.04 / 24.04).
# Safe to run again: keeps .env, the state files and the logs. A server set up with git (/home/tbo/trade3/.git) is
# updated with git pull; otherwise the bot files come from /root/cryptobot.tgz (sent by tbo_servers.bat).
set -e
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
PKG=/root/cryptobot.tgz
D=/home/tbo/trade3/cryptobot

if ! id tbo >/dev/null 2>&1; then
  echo "== first install: system update and Python (a few minutes)"
  apt-get update -qq
  apt-get -y -qq -o Dpkg::Options::=--force-confold -o Dpkg::Options::=--force-confdef upgrade
  apt-get -y -qq install python3 python3-venv
  timedatectl set-ntp true || true
  adduser --disabled-password --gecos "" tbo
fi

mkdir -p /home/tbo/trade3
if [ -d /home/tbo/trade3/.git ]; then
  echo "== this server uses git: pulling the latest code"
  sudo -u tbo git -C /home/tbo/trade3 pull
elif [ -f "$PKG" ]; then
  echo "== copying the bot files"
  tar xzf "$PKG" -C /home/tbo/trade3
fi
rm -f "$PKG"

if [ -f /root/tbo.env ]; then
  mv /root/tbo.env "$D/.env"
fi
chown -R tbo:tbo /home/tbo/trade3
if [ -f "$D/.env" ]; then
  sed -i 's/\r$//' "$D/.env"
  chmod 600 "$D/.env"
fi

cd "$D"
if [ ! -x venv/bin/python ]; then
  echo "== creating the Python environment"
  sudo -u tbo python3 -m venv venv
fi
sudo -u tbo venv/bin/pip install -q --disable-pip-version-check -r requirements.txt

sed -e 's/\r$//' -e 's#/usr/bin/python3#/home/tbo/trade3/cryptobot/venv/bin/python#' tbo.service > /etc/systemd/system/tbo.service
systemctl daemon-reload
ufw allow OpenSSH >/dev/null 2>&1 && ufw --force enable >/dev/null 2>&1 || true

if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
  echo "== clock synchronized"
else
  echo "== clock not synchronized yet (it usually is within a minute)"
fi
echo "== done"

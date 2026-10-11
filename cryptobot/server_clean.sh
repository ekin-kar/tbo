#!/bin/bash
# Server housekeeping for the TBO bot (run as root). Never touches .env, state files or the bot itself.
#   bash server_clean.sh --install   # once (vds_setup.sh does it): weekly automatic cleanup + log limits, then cleans now
#   bash server_clean.sh             # clean now and show the disk / memory use
# What it does: system journal kept 30 days / max 200 MB; the bot's log files (cryptobot/logs/*.log) rotated weekly,
# 8 weeks kept, compressed; apt package cache and unused packages removed; pip cache and temp files older than 7 days.
D=/home/tbo/trade3/cryptobot

if [ "$1" = "--install" ]; then
  mkdir -p /etc/systemd/journald.conf.d
  printf '[Journal]\nSystemMaxUse=200M\nMaxRetentionSec=30day\n' > /etc/systemd/journald.conf.d/tbo.conf
  systemctl restart systemd-journald 2>/dev/null || true
  cat > /etc/logrotate.d/tbo <<EOF
$D/logs/*.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su tbo tbo
}
EOF
  command -v logrotate >/dev/null 2>&1 || apt-get -y -qq install logrotate >/dev/null 2>&1 || true
  install -m 755 "$0" /usr/local/sbin/tbo-clean
  printf '[Unit]\nDescription=TBO weekly server cleanup\n[Service]\nType=oneshot\nExecStart=/usr/local/sbin/tbo-clean\n' \
    > /etc/systemd/system/tbo-clean.service
  printf '[Unit]\nDescription=TBO weekly server cleanup\n[Timer]\nOnCalendar=Sun 04:30\nPersistent=true\n[Install]\nWantedBy=timers.target\n' \
    > /etc/systemd/system/tbo-clean.timer
  rm -f /etc/cron.weekly/tbo-clean
  systemctl daemon-reload 2>/dev/null && systemctl enable --now tbo-clean.timer >/dev/null 2>&1 || true
  echo "== weekly cleanup installed (journal 30 days / 200 MB, bot logs 8 weeks, apt / pip / temp files)"
fi

journalctl --vacuum-time=30d --vacuum-size=200M >/dev/null 2>&1 || true
logrotate /etc/logrotate.d/tbo 2>/dev/null || true
find "$D/logs" -name "*.log.*" -mtime +62 -delete 2>/dev/null || true
apt-get -y -qq autoremove >/dev/null 2>&1 || true
apt-get -y -qq clean >/dev/null 2>&1 || true
rm -rf /root/.cache/pip /home/tbo/.cache/pip 2>/dev/null || true
find /tmp /var/tmp -xdev -type f -mtime +7 -delete 2>/dev/null || true
rm -f /root/cryptobot.tgz /root/tbo.env 2>/dev/null || true

echo "== cleaned"
df -h / | awk 'NR==2 {print "disk: " $3 " used of " $2 " (" $5 "), " $4 " free"}'
free -h | awk 'NR==2 {print "memory: " $3 " used of " $2 ", " $7 " available"}'
du -sh /var/log/journal 2>/dev/null | awk '{print "system logs: " $1}'
du -sh "$D/logs" 2>/dev/null | awk '{print "bot logs: " $1}'

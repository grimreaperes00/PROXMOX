#!/bin/bash
# 共用黃金映像內部清理腳本，適用於 Kali / Ubuntu Template VM
# 建議在轉為 qm template 前執行一次

set -e

echo "[1/6] 清除 machine-id..."
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id

echo "[2/6] 清除 udev 的 persistent net rules..."
rm -f /etc/udev/rules.d/70-persistent-net.rules

if [ -d /etc/cloud ]; then
  echo "[3/6] 清除 cloud-init metadata..."
  rm -rf /etc/cloud/instance /var/lib/cloud/instances/*
fi

echo "[4/6] 清除 DHCP leases..."
rm -f /var/lib/dhcp/* || true

if [ -f /etc/hostname ]; then
  echo "[5/6] 重設 hostname..."
  echo "template-vm" > /etc/hostname
  sed -i '/127.0.1.1/d' /etc/hosts
fi

echo "[6/6] 清除使用者 bash 歷史紀錄..."
unset HISTFILE
rm -f /root/.bash_history

sync

echo "[✅] Template 清理完成，請 shutdown 後使用 qm template 將其轉為黃金映像。"

#!/bin/bash
# Proxmox VE 初期優化腳本
# 功能：安裝Python，停用 enterprise/pve-enterprise 訂閱源，加入 no-subscription，更新升級系統，詢問是否重開機
# Author:
# Date: 2025-04-26

set -e  # 有錯誤立即停止

echo "開始安裝 python3 & python3-pip..."
apt update
apt install -y python3 python3-pip

echo "備份 sources.list..."
cp /etc/apt/sources.list /etc/apt/sources.list.bak

echo "關閉 sources.list 裡面與 enterprise 有關的訂閱源..."
sed -i 's/^\(deb.*enterprise.*\)/#\1/' /etc/apt/sources.list

echo "處理 pve-enterprise.list..."
if [ -f /etc/apt/sources.list.d/pve-enterprise.list ]; then
    cp /etc/apt/sources.list.d/pve-enterprise.list /etc/apt/sources.list.d/pve-enterprise.list.bak
    sed -i 's/^\(deb.*pve-enterprise.*\)/#\1/' /etc/apt/sources.list.d/pve-enterprise.list
fi

echo "新增 no-subscription 套件源..."
echo "deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription" > /etc/apt/sources.list.d/pve-no-subscription.list

echo "更新套件資訊並升級系統..."
apt update
apt dist-upgrade -y

echo "所有操作完成。"

# 問是否要重開機
read -p "需要立即重開機嗎？(y/n): " answer
case "$answer" in
    [Yy]* )
        echo "系統即將重啟..."
        sleep 1
        reboot
        ;;
    [Nn]* )
        echo "請稍後手動重啟系統。"
        ;;
    * )
        echo "無效輸入，請自行手動重啟。"
        ;;
esac


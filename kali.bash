#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

#############
# VARIABLES #
#############
base_url="https://cdimage.kali.org"

echo "[INFO] 偵測 Kali 最新版 QEMU 映像檔 ..."
latest_url=$(curl -s "$base_url" | grep -oP 'href="kali-\d+\.\d+/' | sort -V | tail -n 1 | cut -d'"' -f2)
kali_version="${latest_url//\//}" # e.g. kali-2024.4
kali_url="${base_url}/${kali_version}/${kali_version}-qemu-amd64.7z"

working_dir="$(mktemp -d /tmp/kali-download-XXXXXX)"
trap 'rm -rf "$working_dir"' EXIT

filename="$(basename "$kali_url")"
vm_id=136
vm_name="kali-vm"
vm_description="Kali VM imported from OffSec"
min_memory=4096
max_memory=8192
cpu_cores=4
os_type="l26"
storage_target="local-lvm"
network_bridge="vmbr1"
vlan_id="666" # Leave empty "" for no VLAN

################
# SANITY CHECK #
################
echo "[INFO] 檢查 VM ID 是否已被使用 ..."
if qm status "$vm_id" &>/dev/null; then
  echo "[ERROR] VM ID $vm_id 已被使用，請選用其他 ID。"
  exit 1
fi

################
# DEPENDENCIES #
################
echo "[INFO] 安裝必要套件 (unar)..."
apt-get update -y
apt-get install -y unar wget curl

#################
# CREATE THE VM #
#################
echo "[INFO] 切換至工作資料夾 $working_dir ..."
cd "$working_dir"

echo "[INFO] 下載 Kali QEMU 映像檔：$filename ..."
wget -c --show-progress "$kali_url"

echo "[INFO] 解壓縮映像檔 ..."
unar "$filename"

qcow2file="$(find "$working_dir" -name '*.qcow2' | head -n 1)"
if [ -z "$qcow2file" ]; then
  echo "[ERROR] 找不到 .qcow2 磁碟映像，請確認下載檔案是否正確。"
  exit 1
fi

# 設定網卡
net_config="model=virtio,firewall=0,bridge=${network_bridge}"
if [ -n "$vlan_id" ]; then
  net_config="${net_config},tag=${vlan_id}"
fi

echo "[INFO] 建立 VM ..."
qm create "$vm_id" \
  --memory "$max_memory" --balloon "$min_memory" \
  --cores "$cpu_cores" --name "$vm_name" \
  --description "$vm_description" --net0 "$net_config" \
  --ostype "$os_type" --autostart 1 \
  --startup order=10,up=30,down=30

echo "[INFO] 匯入磁碟檔 ..."
qm importdisk "$vm_id" "$qcow2file" "$storage_target" --format qcow2

echo "[INFO] 掛載磁碟至 VM ..."
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"

echo "[INFO] 設定開機磁碟 ..."
qm set "$vm_id" --boot order=scsi0

echo "[INFO] 啟動 VM ..."
qm start "$vm_id"

echo "[SUCCESS] Kali VM (${kali_version}) 建立完成並已啟動。"


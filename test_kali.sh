#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

echo "========================================="
echo "[0/9] 初始化環境變數 ..."
echo "========================================="

# Kali 最新版偵測與正確拼接 URL
base_url="https://cdimage.kali.org"
latest_url=$(curl -s "$base_url" | grep -oP 'href="kali-\d+\.\d+[a-z]?/' | sort -V | tail -n 1 | cut -d'"' -f2)
kali_folder="${latest_url//\//}"           # 例如 kali-2025.1c
kali_version="${kali_folder#kali-}"         # 取得 2025.1c
filename="kali-linux-${kali_version}-qemu-amd64.7z"
kali_url="${base_url}/${kali_folder}/${filename}"

# 儲存與工作區
storage_base="/var/lib/vz/template/iso/kali-images"
mkdir -p "$storage_base"
working_dir="$storage_base"

# VM 設定
vm_id=136
vm_name="kali-vm"
vm_description="Kali VM imported from OffSec"
min_memory=4096
max_memory=8192
cpu_cores=4
os_type="l26"
storage_target="local-lvm"
network_bridge="vmbr1"
vlan_id="666"

echo "變數初始化完成。"

echo "========================================="
echo "[1/9] 檢查 VM ID 是否已存在 ..."
echo "========================================="
if qm status "$vm_id" &>/dev/null; then
  echo "VM ID $vm_id 已存在，請換一個 ID。"
  exit 1
fi
echo "VM ID 可使用。"

echo "========================================="
echo "[2/9] 確認並安裝必要套件 ..."
echo "========================================="
apt-get update -y
apt-get install -y unar wget curl
echo "必要套件已安裝。"

echo "========================================="
echo "[3/9] 檢查是否已有 Kali 檔案 ..."
echo "========================================="
cd "$working_dir"
if [ -f "$filename" ]; then
  echo "映像檔已存在，跳過下載。"
else
  echo "開始下載 Kali VM 映像檔 ..."
  wget -c --show-progress "$kali_url"
  echo "映像檔下載完成。"
fi

echo "========================================="
echo "[4/9] 解壓縮 Kali 映像檔 ..."
echo "========================================="
unar -f "$filename"
echo "解壓縮完成。"

qcow2file="$(find "$working_dir" -name '*.qcow2' | head -n 1)"
if [ -z "$qcow2file" ]; then
  echo "找不到 qcow2 磁碟映像。"
  exit 1
fi
echo "找到磁碟檔案：$qcow2file"

echo "========================================="
echo "[5/9] 建立 Kali VM ..."
echo "========================================="
if [ -z "$vlan_id" ]; then
  net_config="model=virtio,firewall=0,bridge=${network_bridge}"
else
  net_config="model=virtio,firewall=0,bridge=${network_bridge},tag=${vlan_id}"
fi

qm create "$vm_id" \
  --memory "$max_memory" --balloon "$min_memory" \
  --cores "$cpu_cores" --name "$vm_name" \
  --description "$vm_description" --net0 "$net_config" \
  --ostype "$os_type" --autostart 1 \
  --startup order=10,up=30,down=30
echo "VM 建立完成。"

echo "========================================="
echo "[6/9] 匯入 Kali 磁碟到 Storage ..."
echo "========================================="
qm importdisk "$vm_id" "$qcow2file" "$storage_target" --format qcow2
echo "磁碟匯入完成。"

echo "========================================="
echo "[7/9] 掛載磁碟並設定開機順序 ..."
echo "========================================="
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"
qm set "$vm_id" --boot order=scsi0
echo "磁碟掛載與開機設定完成。"

echo "========================================="
echo "[8/9] 啟動 Kali VM ..."
echo "========================================="
qm start "$vm_id"
echo "Kali VM 已成功啟動。"

echo "========================================="
echo "[9/9] 完成所有作業。映像檔儲存於：$working_dir"
echo "========================================="

#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

echo "========================================="
echo "[0/9] 初始化環境變數 ..."
echo "========================================="

# 從 Kali 官方 cdimage.kali.org 取得最新正式版（含a、b、c排序）
base_url="https://cdimage.kali.org/"
echo "[INFO] 從 Kali 官方 cdimage.kali.org 抓取最新正式版目錄..."

latest_dir=$(curl -s "$base_url" | grep -oP 'kali-\d+\.\d+[a-z]?/' | sort -rV | head -n 1)

if [ -z "$latest_dir" ]; then
    echo "[ERROR] 找不到 Kali 版本目錄，請檢查網路或官方站。"
    exit 1
fi

kali_version="${latest_dir%/}" # 去除最後的 /
kali_url="${base_url}${kali_version}/${kali_version}-qemu-amd64.7z"
filename="${kali_version}-qemu-amd64.7z"

echo "[INFO] 解析得到 Kali 最新版：$kali_version"
echo "[INFO] 預備下載連結：$kali_url"

# 儲存與工作資料夾
storage_base="/var/lib/vz/template/iso/kali-images"
mkdir -p "$storage_base"
working_dir="$storage_base"

# VM 基本設定
vm_id=136
vm_name="kali-vm"
vm_description="Kali VM imported automatically"
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
    echo "VM ID $vm_id 已存在，請選一個未使用的 ID。"
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
echo "[3/9] 檢查是否已有 Kali 映像檔 ..."
echo "========================================="
cd "$working_dir"
if [ -f "$filename" ]; then
    echo "映像檔已存在，跳過下載。"
else
    echo "開始下載 Kali QEMU 映像檔 ..."
    wget -c --show-progress "$kali_url"
    echo "下載完成。"
fi

echo "========================================="
echo "[4/9] 解壓縮 Kali 映像檔 ..."
echo "========================================="
unar -f "$filename"
echo "解壓縮完成。"

# 使用 find 避免引數過長
qcow2file="$(find "$working_dir" -type f -name '*.qcow2' | head -n 1)"
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
qm set "$vm_id" --boot order=scsi0 --bootdisk scsi0
echo "磁碟掛載與開機設定完成。"

echo "========================================="
echo "[8/9] 啟動 Kali VM ..."
echo "========================================="
qm start "$vm_id"
echo "Kali VM 已成功啟動。"

echo "========================================="
echo "[9/9] 作業完成，映像儲存於：$working_dir"
echo "========================================="

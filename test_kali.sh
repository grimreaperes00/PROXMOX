#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

# ==========================
# 自動化安裝 Kali VM & 清除舊版本
# ==========================

# 確認必須以 root 身份執行
if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] 此腳本需要以 root 權限執行！"
  exit 1
fi

echo "========================================="
echo "[0/11] 初始化環境變數與 VM ID ..."
echo "========================================="

# 抓取 Kali 最新版
base_url="https://cdimage.kali.org/"
latest_dir=$(curl -sf "$base_url" | grep -oP 'kali-\d+\.\d+[a-z]?/' | sort -rV | head -n 1)

if [ -z "$latest_dir" ]; then
  echo "[ERROR] 找不到 Kali 版本目錄，請檢查網路或官方站。"
  exit 1
fi

kali_version_dir="${latest_dir%/}"       # 例如 kali-2025.1c
kali_version="${kali_version_dir#kali-}"  # 例如 2025.1c

filename="kali-linux-${kali_version}-qemu-amd64.7z"
kali_url="${base_url}${kali_version_dir}/${filename}"
existing_file="$working_dir/$filename"

echo "========================================="
echo "[比對] 是否已有最新版 Kali 映像檔 ..."
echo "========================================="

if [ -f "$existing_file" ]; then
  echo "[SKIP] 已存在最新版映像檔：$existing_file"
  skip_download=true
else
  echo "[INFO] 舊映像不存在或非最新版，清除資料夾：$working_dir"
  rm -rf "${working_dir:?}/"*
  skip_download=false
fi

# 下載區段
if [ "$skip_download" = false ]; then
  echo "[INFO] 開始下載 Kali 映像檔 ..."
  wget -c --retry-connrefused --tries=5 --show-progress "$kali_url"
  echo "[OK] 下載完成。"
else
  echo "[INFO] 跳過下載。"
fi

# ==========================
echo "========================================="
echo "[2/11] 自動尋找可用 VM ID ..."
echo "========================================="
start_id=136
while qm status "$start_id" &>/dev/null; do
  ((start_id++))
done
vm_id=$start_id
echo "[INFO] 使用 VM ID：$vm_id"

# VM 基本設定
vm_name="kali-vm"
vm_description="Kali VM imported automatically"
min_memory=4096
max_memory=8192
cpu_cores=4
os_type="l26"
storage_target="local-lvm"
network_bridge="vmbr0"
vlan_id=""
disk_expand_size="+20G"

# ==========================
echo "========================================="
echo "[3/11] 安裝必要套件 ..."
echo "========================================="
apt-get update -y
apt-get install -y unar wget curl
echo "[SUCCESS] 套件已安裝。"

# ==========================
echo "========================================="
echo "[4/11] 下載 Kali 最新版 QEMU 映像 ..."
echo "========================================="
cd "$working_dir"
wget -c --retry-connrefused --tries=5 --show-progress "$kali_url"
echo "[SUCCESS] 映像下載完成。"

# ==========================
echo "========================================="
echo "[5/11] 解壓縮 Kali QEMU ..."
echo "========================================="
unar -f "$filename"
echo "[SUCCESS] 解壓完成。"

# ==========================
echo "========================================="
echo "[6/11] 搜尋解壓後 qcow2 磁碟 ..."
echo "========================================="
qcow2file="$(find "$working_dir" -type f -name '*.qcow2' | head -n 1)"
if [ -z "$qcow2file" ]; then
  echo "[ERROR] 找不到 qcow2 映像！"
  exit 1
fi
echo "[INFO] 找到 qcow2 映像：$qcow2file"

# ==========================
echo "========================================="
echo "[7/11] 建立 Kali VM ..."
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
  --startup order=10,up=30,down=30 \
  --machine q35
echo "[SUCCESS] VM 建立完成。"

# ==========================
echo "========================================="
echo "[8/11] 匯入 Kali 磁碟到 Storage ..."
echo "========================================="
qm importdisk "$vm_id" "$qcow2file" "$storage_target" --format qcow2
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"
qm resize "$vm_id" scsi0 "$disk_expand_size"
echo "[OK] 磁碟匯入與擴充完成（$disk_expand_size）""

# ==========================
echo "========================================="
echo "[9/11] 掛載磁碟並設定開機順序 ..."
echo "========================================="
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"
qm set "$vm_id" --boot order=scsi0 --bootdisk scsi0
echo "[SUCCESS] 磁碟掛載與開機設定完成。"

# ==========================
echo "========================================="
echo "[10/11] 啟動 Kali VM ..."
echo "========================================="
qm start "$vm_id"
echo "[SUCCESS] Kali VM (${vm_id}) 啟動成功。"

# ==========================
echo "========================================="
echo "[11/11] 最後確認 VM 狀態 ..."
echo "========================================="
qm status "$vm_id"
echo "[FINISH] 全部作業完成！"

echo ""
echo " Kali images 路徑：$working_dir"
echo " VM ID：$vm_id"
echo " 請至 Proxmox GUI 檢視您的 Kali VM！"

#!/bin/bash
set -euo pipefail
IFS=$'\n\t'

echo "========================================="
echo "[0/11] 初始化環境變數與 VM ID ..."
echo "========================================="

base_url="https://cdimage.kali.org/"
latest_dir=$(curl -sf "$base_url" | grep -oP 'kali-\d+\.\d+[a-z]?/' | sort -rV | head -n 1)

if [ -z "$latest_dir" ]; then
  echo "[ERROR] 無法取得 Kali 最新版本目錄！"
  exit 1
fi

kali_version_dir="${latest_dir%/}"
kali_version="${kali_version_dir#kali-}"
filename="kali-linux-${kali_version}-qemu-amd64.7z"
kali_url="${base_url}${kali_version_dir}/${filename}"

working_dir="/var/lib/vz/template/iso/kali-images"
mkdir -p "$working_dir"
existing_file="$working_dir/$filename"

echo "[INFO] 最新 Kali 資料夾：$kali_version_dir"
echo "[INFO] 最新 Kali 檔案：$filename"
echo "[INFO] 下載連結：$kali_url"

echo "========================================="
echo "[1/11] 比對是否已有最新 Kali 映像 ..."
echo "========================================="

if [ -f "$existing_file" ]; then
  echo "[SKIP] 已存在最新版映像：$existing_file"
  skip_download=true
else
  echo "[INFO] 映像不存在或為舊版本，清除資料夾：$working_dir"
  rm -rf "${working_dir:?}/"*
  skip_download=false
fi

echo "========================================="
echo "[2/11] 尋找可用 VM ID ..."
echo "========================================="
start_id=136
while qm status "$start_id" &>/dev/null; do
  ((start_id++))
done
vm_id=$start_id
echo "[INFO] 使用 VM ID：$vm_id"

echo "========================================="
echo "[3/11] 設定 VM 基礎配置 ..."
echo "========================================="
vm_name="kali-vm"
vm_description="Kali VM imported automatically"
min_memory=4096
max_memory=8192
cpu_cores=4
os_type="l26"
storage_target="local-lvm"
network_bridge="vmbr0"
vlan_id=""
expand_gb=0
echo "[OK] 基本參數已設定"

echo "========================================="
echo "[4/11] 安裝必要套件 ..."
echo "========================================="
apt-get update -y
apt-get install -y unar wget curl
echo "[OK] 必要套件已安裝"

echo "========================================="
echo "[5/11] 下載 Kali QEMU 映像 ..."
echo "========================================="
cd "$working_dir"
if [ "$skip_download" = false ]; then
  wget -c --retry-connrefused --tries=5 --show-progress "$kali_url"
  echo "[OK] 映像下載完成。"
else
  echo "[INFO] 跳過下載"
fi

echo "========================================="
echo "[6/11] 解壓縮 Kali 映像 ..."
echo "========================================="
unar -f "$filename"
echo "[OK] 解壓縮完成"

echo "========================================="
echo "[7/11] 搜尋 .qcow2 磁碟映像 ..."
echo "========================================="
qcow2file="$(find "$working_dir" -type f -name '*.qcow2' | head -n 1)"
if [ -z "$qcow2file" ]; then
  echo "[ERROR] 找不到 qcow2 磁碟映像！"
  exit 1
fi
echo "[INFO] 找到映像檔：$qcow2file"

echo "========================================="
echo "[8/11] 建立 Kali VM ..."
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
echo "[OK] VM 建立完成"

echo "========================================="
echo "[9/11] 匯入並擴充 Kali 磁碟 ..."
echo "========================================="
qm importdisk "$vm_id" "$qcow2file" "$storage_target" --format qcow2
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"

raw_size=$(qm config "$vm_id" | grep -Po 'scsi0:.*size=\K\d+(\.\d+)?(?=G)' || true)

if [ -z "$raw_size" ]; then
  echo "[WARN] 無法解析磁碟大小，略過擴充"
else
  current_size_gb=$(printf "%.0f" "$raw_size")
  new_size_gb=$((current_size_gb + expand_gb))
  echo "[INFO] 當前磁碟大小：${current_size_gb}G，擴充後大小：${new_size_gb}G"
  qm resize "$vm_id" scsi0 "${new_size_gb}G"
  echo "[OK] 磁碟已擴充至 ${new_size_gb}G"
fi

echo "========================================="
echo "[10/11] 設定開機磁碟與檢查 KVM 狀態 ..."
echo "========================================="

qm set "$vm_id" --boot order=scsi0 --bootdisk scsi0
echo "[OK] 已設為開機磁碟"

if [ ! -e /dev/kvm ]; then
  echo "[WARN] 檢測到系統未啟用 KVM，將關閉 VM 的 KVM 虛擬化..."
  qm set "$vm_id" --kvm 0
  echo "[OK] 已設定 CPU 模型為 host 並關閉 KVM 虛擬化"
else
  echo "[INFO] KVM 已啟用，將保持預設虛擬化設定"
fi

echo "========================================="
echo "[11/11] 啟動 Kali VM ..."
echo "========================================="
qm start "$vm_id"
echo "[OK] VM 啟動成功"

echo ""
echo "========================================="
echo " Kali VM 建立與啟動完成！"
echo " 儲存資料夾：$working_dir"
echo " 擴充磁碟：+${expand_gb}G"
echo "  VM ID：$vm_id"

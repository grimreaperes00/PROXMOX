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

template_id=999
clone_script="./kali_clone_vm.sh"
prepare_script="./template_prepare.sh"

if [ -f "$existing_file" ]; then
  echo "[SKIP] 已存在最新版映像：$existing_file"
  skip_download=true
else
  echo "[INFO] 映像不存在或為舊版本，清除資料夾：$working_dir"
  rm -rf "${working_dir:?}/"*
  skip_download=false

  # 🧨 偵測並刪除舊的 template VM（若存在）
  if qm status "$template_id" &>/dev/null; then
    echo "[WARN] 偵測到舊版 Template VM（ID: $template_id），將移除以重建"
    qm destroy "$template_id" --purge
    echo "[OK] 舊 Template VM 已刪除"
  fi
fi

echo "========================================="
echo "[1.5/11] 偵測是否已有黃金映像 Template VM ..."
echo "========================================="

if qm status "$template_id" &>/dev/null && qm config "$template_id" | grep -q "^template: 1"; then
  echo "[SKIP] 已存在黃金映像 VM（ID: $template_id）"
  if [ -x "$clone_script" ]; then
    echo "[INFO] 偵測到 clone 腳本，跳轉執行：$clone_script"
    exec "$clone_script" "$@"
  else
    echo "[WARN] 找到 template，但未偵測到可執行的 clone 腳本：$clone_script"
    echo "[提示] 請確認腳本名稱與執行權限正確（chmod +x）"
    exit 1
  fi
else
  echo "[INFO] 尚未建立黃金映像 VM，將繼續建構流程..."
fi

echo "========================================="
echo "[2/11] 使用固定 VM ID 建立黃金映像 ..."
echo "========================================="
vm_id=$template_id
echo "[INFO] 使用 VM ID：$vm_id"

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
echo "[8/11] 建立 Kali Template VM ..."
echo "========================================="
qm create "$vm_id" \
  --name "kali-template" \
  --ostype l26
echo "[OK] Template VM 建立完成"

echo "========================================="
echo "[9/11] 匯入 Kali 磁碟 ..."
echo "========================================="
qm importdisk "$vm_id" "$qcow2file" "local-lvm" --format qcow2
qm set "$vm_id" --scsi0 "local-lvm:vm-${vm_id}-disk-0"
qm set "$vm_id" --boot order=scsi0

echo "========================================="
echo "[10/11] 跳轉清理腳本以準備轉為 Template ..."
echo "========================================="
if [ -x "$prepare_script" ]; then
  echo "[INFO] 執行清理腳本：$prepare_script"
  exec "$prepare_script" "$vm_id" "$@"
else
  echo "[ERROR] 找不到清理腳本或無執行權限：$prepare_script"
  exit 1
fi

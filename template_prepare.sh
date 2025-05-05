#!/bin/bash
# 通用黃金映像清理啟動腳本（簡化）
# 用法：./template_prepare.sh <vm_id> [clone_args...]

set -euo pipefail
IFS=$'\n\t'

vm_id="${1:-}"
shift || true

if [ -z "$vm_id" ] || ! [[ "$vm_id" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] 請提供合法的 VM ID 作為參數！"
  echo "用法：./template_prepare.sh <vm_id> [clone_args...]"
  exit 1
fi

clone_args=("$@")
clone_script="./kali_clone_vm.sh"

# 啟動 VM
echo "========================================="
echo "[1/3] 啟動 VM (ID: $vm_id) 進行清理準備..."
echo "========================================="
qm start "$vm_id"
echo "[提示] 請登入 VM 並手動執行 /root/template_prepare_inner.sh 完成清理，再關機。"
read -p "當您完成清理並關機後，請按 Enter 繼續..."

# 檢查 VM 是否關機
until qm status "$vm_id" | grep -q "status: stopped"; do
  echo "[等待] VM 尚未關機，請確認已關閉 VM..."
  sleep 5
done

echo "========================================="
echo "[2/3] 設定 VM 為 Template 模式..."
echo "========================================="
qm template "$vm_id"
echo "[OK] VM 已成功轉換為黃金映像 Template"

echo "========================================="
echo "[3/3] 跳轉執行 clone 腳本..."
echo "========================================="
if [ -x "$clone_script" ]; then
  echo "[INFO] 執行 clone 腳本：$clone_script"
  exec "$clone_script" "${clone_args[@]}"
else
  echo "[ERROR] clone 腳本不存在或無執行權限：$clone_script"
  exit 1
fi

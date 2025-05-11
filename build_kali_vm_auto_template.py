#!/usr/bin/env python3
# 自動建立 Kali Template 並批次建立 VM，集中顯示所有 VM 資訊
# 若偵測到新版 Kali QEMU 映像，會清空原始資料夾並刪除黃金映像 VM（ID 9000）

import os
import re
import subprocess
import requests
import argparse
import json
import time
from pathlib import Path

# 固定黃金映像 VM ID
TEMPLATE_ID = 9000

# 從 Kali 官方網站解析最新版本與下載連結
def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄！")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

# 判斷 VM ID 是否被使用中
def id_in_use(vm_id: int) -> bool:
    vm_check = subprocess.run(["qm", "status", str(vm_id)], stdout=subprocess.DEVNULL)
    ct_check = subprocess.run(["pct", "status", str(vm_id)], stdout=subprocess.DEVNULL)
    return vm_check.returncode == 0 or ct_check.returncode == 0

# 從指定 ID 起尋找未佔用的 VM ID
def find_available_vm_id(start: int = 100):
    while id_in_use(start):
        start += 1
    return start

# 從 VM 配置中讀取 scsi0 的磁碟大小
def get_disk_size_gb(vm_id: int, storage: str) -> str:
    result = subprocess.run(["qm", "config", str(vm_id)], stdout=subprocess.PIPE, text=True)
    for line in result.stdout.splitlines():
        if line.strip().startswith("scsi0:") and f"{storage}:" in line:
            for p in line.split(","):
                if p.strip().startswith("size="):
                    return p.split("=")[-1]
    return "未知"

# 將單位轉為 GiB 顯示
def convert_to_gb(size_str: str) -> str:
    size_str = size_str.strip().upper()
    if size_str.endswith("G"):
        return size_str
    elif size_str.endswith("M"):
        return f"{float(size_str[:-1]) / 1024:.1f}G"
    elif size_str.endswith("K"):
        return f"{float(size_str[:-1]) / (1024 * 1024):.2f}G"
    return size_str

# 等待 VM 啟動後取得 IP（透過 qemu-guest-agent）
def wait_for_ip(vm_id, retries=10, delay=3):
    for _ in range(retries):
        try:
            result = subprocess.run(["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and "ip-addresses" in result.stdout:
                data = json.loads(result.stdout)
                for interface in data:
                    # 跳過 loopback (lo)
                    if interface.get("name") == "lo":
                        continue
                    for ip in interface.get("ip-addresses", []):
                        if ip.get("ip-address-type") == "ipv4" and ip.get("ip-address") != "127.0.0.1":
                            return ip.get("ip-address")
        except Exception:
            pass
        time.sleep(delay)
    return "未知"

# 建立黃金映像模板，若版本不同則自動刪除舊有黃金映像 VM 並更新
def create_template(args):
    vm_id = TEMPLATE_ID
    working_dir = Path(args.workdir).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)

    # 抓取最新版 Kali QEMU 映像資訊
    kali_dir, version, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    iso_path = working_dir / filename
    version_file = working_dir / ".kali_version"

    # 判斷版本是否有更新
    version_changed = True
    if version_file.exists():
        with version_file.open() as vf:
            current_version = vf.read().strip()
            if current_version == version:
                version_changed = False

    # 若版本不同 → 清空映像檔與刪除 VM ID 9000
    if version_changed:
        print(f"[INFO] 偵測到新版 Kali：{version}，清除舊有映像與 template VM ...")
        for f in working_dir.glob("*"):
            f.unlink()
        template_conf = Path(f"/etc/pve/qemu-server/{vm_id}.conf")
        if template_conf.exists():
            print(f"[INFO] 刪除 VM ID {vm_id} ...")
            subprocess.run(["qm", "destroy", str(vm_id)], check=True)
        with version_file.open("w") as vf:
            vf.write(version)

    # 映像檔不存在就下載
    if not iso_path.exists():
        print(f"[INFO] 下載 Kali 映像：{kali_url}")
        subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5", "--show-progress", kali_url], check=True)
    else:
        print(f"[SKIP] 映像已存在：{filename}")

    # 解壓縮 .qcow2
    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        print("[INFO] 解壓縮 Kali 映像 ...")
        subprocess.run(["unar", "-f", filename], check=True)
        print("[OK] 解壓縮完成")
    else:
        print(f"[SKIP] 偵測到已解壓：{qcow2file.name}")

    os.chdir(working_dir)
    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        raise RuntimeError("找不到 qcow2 映像！")

    # 建立黃金映像 VM 並轉為 template
    subprocess.run(["qm", "create", str(vm_id),
                    "--memory", str(args.max_mem),
                    "--balloon", str(args.min_mem),
                    "--cores", str(args.cpu),
                    "--name", "kali-template",
                    "--description", "Kali Golden Image Template",
                    "--net0", f"model=virtio,bridge={args.bridge}",
                    "--ostype", "l26",
                    "--machine", "q35"], check=True)
    subprocess.run(["qm", "importdisk", str(vm_id), str(qcow2file), args.storage, "--format", "qcow2"], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--scsi0", f"{args.storage}:vm-{vm_id}-disk-0"], check=True)
    subprocess.run(["qm", "resize", str(vm_id), "scsi0", args.resize], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)
    subprocess.run(["qm", "template", str(vm_id)], check=True)
    print(f"[OK] Template VM 已建立於 ID {vm_id}")

# 複製 template 並部署一台 VM
def deploy_vm(args, vm_index=None):
    vm_id = find_available_vm_id(100)
    name = args.name if vm_index is None else f"{args.name}-{vm_index+1}"
    desc = args.description if vm_index is None else f"{args.description} #{vm_index+1}"
    net_config = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net_config += f",tag={args.vlan}"

    subprocess.run(["qm", "clone", str(TEMPLATE_ID), str(vm_id), "--name", name], check=True)
    subprocess.run(["qm", "set", str(vm_id),
                    "--memory", str(args.max_mem),
                    "--balloon", str(args.min_mem),
                    "--cores", str(args.cpu),
                    "--net0", net_config,
                    "--description", desc,
                    "--agent", "enabled=1"], check=True)
    subprocess.run(["qm", "start", str(vm_id)], check=True)

    ip = wait_for_ip(vm_id)
    disk = get_disk_size_gb(vm_id, args.storage)

    return {
        "vm_id": vm_id,
        "name": name,
        "ip": ip,
        "cpu": args.cpu,
        "ram": f"{args.min_mem} ~ {args.max_mem} MB",
        "disk": convert_to_gb(disk)
    }

# 主流程：建立黃金映像（如需），部署多台 VM 並集中顯示
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali Template 並批次建立 VM（集中顯示資訊）")
    parser.add_argument("--count", type=int, default=1, help="要建立的 VM 數量")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images", help="工作目錄")
    parser.add_argument("--name", default="kali-vm", help="VM 名稱")
    parser.add_argument("--description", default="Kali VM auto-generated", help="VM 說明")
    parser.add_argument("--min-mem", type=int, default=4096, help="最小記憶體")
    parser.add_argument("--max-mem", type=int, default=8192, help="最大記憶體")
    parser.add_argument("--cpu", type=int, default=4, help="CPU 核心數")
    parser.add_argument("--bridge", default="vmbr0", help="網路橋接")
    parser.add_argument("--vlan", type=str, help="VLAN ID")
    parser.add_argument("--resize", default="+20G", help="磁碟擴充大小")
    parser.add_argument("--storage", default="local-lvm", help="儲存目標名稱")
    args = parser.parse_args()

    if not Path(f"/etc/pve/qemu-server/{TEMPLATE_ID}.conf").exists():
        print(f"[INFO] 尚未存在黃金映像，開始建立 ...")
        create_template(args)

    all_vms = []
    for i in range(args.count):
        info = deploy_vm(args, i)
        all_vms.append(info)

    # 最後集中輸出所有 VM 狀態
    print("\n=== 所有 Kali VM 建立完成 ===\n")
    for vm in all_vms:
        print(f"📌 VM {vm['name']} (ID: {vm['vm_id']})")
        print(f"🧠 記憶體：{vm['ram']}")
        print(f"🧮 CPU：{vm['cpu']}")
        print(f"💾 磁碟：{vm['disk']}")
        print(f"🌐 IP：{vm['ip']}\n")

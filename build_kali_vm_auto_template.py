#!/usr/bin/env python3
# 完整防呆版 Kali VM 自動部署腳本
# 功能：版本檢查、自動下載與解壓、黃金映像建立、多台 VM 複製與集中顯示資訊

import os
import re
import subprocess
import requests
import argparse
import json
import time
from pathlib import Path

TEMPLATE_ID = 9000  # 固定的黃金映像 VM ID

# 從 Kali 官方網站取得最新 QEMU 映像資訊
def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

# 判斷 VM ID 是否已存在
def id_in_use(vm_id: int) -> bool:
    return subprocess.run(["qm", "status", str(vm_id)], stdout=subprocess.DEVNULL).returncode == 0

# 從指定起始值向上找可用 VM ID
def find_available_vm_id(start: int = 100):
    while id_in_use(start):
        start += 1
    return start

# 擷取 VM 設定中磁碟大小資訊
def get_disk_size_gb(vm_id: int, storage: str) -> str:
    result = subprocess.run(["qm", "config", str(vm_id)], stdout=subprocess.PIPE, text=True)
    for line in result.stdout.splitlines():
        if "scsi0:" in line and f"{storage}:" in line:
            for part in line.split(","):
                if part.startswith("size="):
                    return part.split("=")[1]
    return "未知"

# 將容量字串轉為 GiB 格式
def convert_to_gb(size_str: str) -> str:
    if size_str.endswith("G"):
        return size_str
    elif size_str.endswith("M"):
        return f"{float(size_str[:-1]) / 1024:.1f}G"
    elif size_str.endswith("K"):
        return f"{float(size_str[:-1]) / (1024 * 1024):.2f}G"
    return size_str

# 等待 guest agent 傳回 VM 的 IP
def wait_for_ip(vm_id, retries=10, delay=3):
    for _ in range(retries):
        try:
            result = subprocess.run(["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for iface in data:
                    if iface.get("name") == "lo":
                        continue
                    for ip in iface.get("ip-addresses", []):
                        if ip.get("ip-address-type") == "ipv4" and ip.get("ip-address") != "127.0.0.1":
                            return ip.get("ip-address")
        except Exception:
            pass
        time.sleep(delay)
    return "未知"

# 建立黃金映像 template
def create_template(args, version):
    vm_id = TEMPLATE_ID
    working_dir = Path(args.workdir).resolve()
    kali_dir, _, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    iso_path = working_dir / filename
    version_file = working_dir / ".kali_version"

    print(f"[INFO] 下載 Kali 映像：{kali_url}")
    subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5", "--show-progress", kali_url], check=True)

    print("[INFO] 清空工作目錄 ...")
    for f in working_dir.glob("*"):
        if f.name != filename:
            f.unlink()

    print("[INFO] 解壓縮 Kali QEMU 映像 ...")
    subprocess.run(["unar", "-f", filename], check=True)

    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        raise RuntimeError("找不到解壓後的 qcow2 映像！")

    if Path(f"/etc/pve/qemu-server/{vm_id}.conf").exists():
        print(f"[INFO] 刪除舊的黃金映像 VM（ID {vm_id}）")
        subprocess.run(["qm", "destroy", str(vm_id)], check=True)

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

    with version_file.open("w") as vf:
        vf.write(version)

    print(f"[OK] 黃金映像 VM 已建立完成（ID: {vm_id}）")

# 建立並設定一台 Kali VM
def deploy_vm(args, vm_index=None):
    vm_id = find_available_vm_id(100)
    name = args.name if vm_index is None else f"{args.name}-{vm_index+1}"
    desc = args.description if vm_index is None else f"{args.description} #{vm_index+1}"
    net = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net += f",tag={args.vlan}"

    subprocess.run(["qm", "clone", str(TEMPLATE_ID), str(vm_id), "--name", name], check=True)
    subprocess.run(["qm", "set", str(vm_id),
                    "--memory", str(args.max_mem),
                    "--balloon", str(args.min_mem),
                    "--cores", str(args.cpu),
                    "--net0", net,
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

# 主程式入口
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali Template 並快速複製多台 VM")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images")
    parser.add_argument("--name", default="kali-vm")
    parser.add_argument("--description", default="Kali VM auto-generated")
    parser.add_argument("--min-mem", type=int, default=4096)
    parser.add_argument("--max-mem", type=int, default=8192)
    parser.add_argument("--cpu", type=int, default=4)
    parser.add_argument("--bridge", default="vmbr0")
    parser.add_argument("--vlan", type=str)
    parser.add_argument("--resize", default="+20G")
    parser.add_argument("--storage", default="local-lvm")
    args = parser.parse_args()

    working_dir = Path(args.workdir)
    version_file = working_dir / ".kali_version"
    template_conf = Path(f"/etc/pve/qemu-server/{TEMPLATE_ID}.conf")
    qcow2file = next(working_dir.glob("*.qcow2"), None)
    _, version, _, _ = get_latest_kali_url("https://cdimage.kali.org/")

    version_changed = True
    if version_file.exists():
        with version_file.open() as vf:
            if vf.read().strip() == version:
                version_changed = False

    # 判斷是否需要重新建立黃金映像
    if not template_conf.exists() or not qcow2file or version_changed:
        print(f"[INFO] 偵測到以下情況需建立黃金映像：")
        if not template_conf.exists(): print("  - VM 9000 不存在")
        if not qcow2file: print("  - 缺少 qcow2 映像")
        if version_changed: print(f"  - 偵測到 Kali 發行新版：{version}")
        create_template(args, version)

    # 建立多台 VM 並集中顯示資訊
    all_vms = []
    for i in range(args.count):
        all_vms.append(deploy_vm(args, i))

    print("\n=== 所有 Kali VM 建立完成 ===\n")
    for vm in all_vms:
        print(f"📌 VM {vm['name']} (ID: {vm['vm_id']})")
        print(f"🧠 記憶體：{vm['ram']}")
        print(f"🧮 CPU：{vm['cpu']}")
        print(f"💾 磁碟：{vm['disk']}")
        print(f"🌐 IP：{vm['ip']}\n")

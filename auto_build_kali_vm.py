#!/usr/bin/env python3
import os
import re
import subprocess
import requests
import argparse
import json
import time
import shutil
from pathlib import Path

TEMPLATE_ID = 9000  # 固定的黃金映像 VM ID

def ensure_installed(package_name):
    if shutil.which(package_name) is None:
        print(f"[INFO] 未安裝 {package_name}，正在安裝 ...")
        subprocess.run(["apt", "update"], check=True)
        subprocess.run(["apt", "install", "-y", package_name], check=True)
    else:
        print(f"[SKIP] 已安裝 {package_name}，跳過安裝")

def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

def id_in_use(vm_id: int) -> bool:
    return subprocess.run(["qm", "status", str(vm_id)], stdout=subprocess.DEVNULL).returncode == 0

def find_available_vm_id(start: int = 100):
    while id_in_use(start):
        start += 1
    return start

def get_disk_size_gb(vm_id: int, storage: str) -> str:
    result = subprocess.run(["qm", "config", str(vm_id)], stdout=subprocess.PIPE, text=True)
    for line in result.stdout.splitlines():
        if "scsi0:" in line and f"{storage}:" in line:
            for part in line.split(","):
                if part.startswith("size="):
                    return part.split("=")[1]
    return "未知"

def convert_to_gb(size_str: str) -> str:
    if size_str.endswith("G"):
        return size_str
    elif size_str.endswith("M"):
        return f"{float(size_str[:-1]) / 1024:.1f}G"
    elif size_str.endswith("K"):
        return f"{float(size_str[:-1]) / (1024 * 1024):.2f}G"
    return size_str

def wait_for_ip(vm_id, retries=10, delay=3):
    for _ in range(retries):
        try:
            result = subprocess.run(
                ["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for iface in data:
                    if iface.get("name") not in ["eth0", "ens18", "ens3", "enp0s3"]:
                        continue
                    for ip in iface.get("ip-addresses", []):
                        if ip.get("ip-address-type") == "ipv4" and ip.get("ip-address") != "127.0.0.1":
                            return ip.get("ip-address")
        except Exception:
            pass
        time.sleep(delay)
    return "未知"

def create_template(args, version):
    vm_id = TEMPLATE_ID
    working_dir = Path(args.workdir).resolve()
    kali_dir, _, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    iso_path = working_dir / filename
    version_file = working_dir / ".kali_version"

    working_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] 下載 Kali 映像：{kali_url}")
    subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5", "--show-progress", kali_url],
                   check=True, cwd=working_dir)

    print("[INFO] 清空工作目錄中其他檔案 ...")
    for f in working_dir.glob("*"):
        if f.name != filename:
            f.unlink()

    print("[INFO] 解壓縮 Kali QEMU 映像 ...")
    subprocess.run(["unar", "-f", filename], check=True, cwd=working_dir)

    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        raise RuntimeError("找不到解壓後的 qcow2 映像")

    if Path(f"/etc/pve/qemu-server/{vm_id}.conf").exists():
        print(f"[INFO] 刪除舊的黃金映像 VM（ID {vm_id}）")
        subprocess.run(["qm", "destroy", str(vm_id)], check=True)

    print("[INFO] 建立黃金映像 VM ...")
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

    print(f"[OK] Template VM 已建立完成（ID: {vm_id}）")

def deploy_vm(args, vm_name, index=None):
    vm_id = find_available_vm_id(100)
    desc = args.description if index is None else f"{args.description} #{index+1}"
    net = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net += f",tag={args.vlan}"

    subprocess.run(["qm", "clone", str(TEMPLATE_ID), str(vm_id), "--name", vm_name], check=True)
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
        "name": vm_name,
        "ip": ip,
        "cpu": args.cpu,
        "ram": f"{args.min_mem} ~ {args.max_mem} MB",
        "disk": convert_to_gb(disk)
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali Template 並快速複製多台 VM")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--name", nargs='+', default=["kali-vm"], help="VM 名稱，支援單一名稱或多個名稱")
    parser.add_argument("--description", default="Kali VM auto-generated")
    parser.add_argument("--min-mem", type=int, default=4096)
    parser.add_argument("--max-mem", type=int, default=8192)
    parser.add_argument("--cpu", type=int, default=4)
    parser.add_argument("--bridge", default="vmbr0")
    parser.add_argument("--vlan", type=str)
    parser.add_argument("--resize", default="+20G")
    parser.add_argument("--storage", default="local-lvm")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images")
    args = parser.parse_args()

    if len(args.name) == 1:
        vm_names = [args.name[0]] + [f"{args.name[0]}-{i}" for i in range(1, args.count)]
    elif len(args.name) == args.count:
        vm_names = args.name
    else:
        raise ValueError(f"[ERROR] VM 名稱數量（{len(args.name)}）與 --count（{args.count}）不一致")

    ensure_installed("unar")

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

    if not template_conf.exists() or not qcow2file or version_changed:
        print(f"[INFO] 偵測到以下情況需建立黃金映像：")
        if not template_conf.exists(): print("  - VM 9000 不存在")
        if not qcow2file: print("  - 缺少 qcow2 映像")
        if version_changed: print(f"  - 發現新版 Kali：{version}")
        create_template(args, version)

    all_vms = []
    for i in range(args.count):
        all_vms.append(deploy_vm(args, vm_names[i], i))

    print("\n=== 所有 Kali VM 建立完成 ===\n")
    for vm in all_vms:
        print(f"📌 VM {vm['name']} (ID: {vm['vm_id']})")
        print(f"🧠 記憶體：{vm['ram']}")
        print(f"🧮 CPU：{vm['cpu']}")
        print(f"💾 磁碟：{vm['disk']}")
        print(f"🌐 IP：{vm['ip']}\n")

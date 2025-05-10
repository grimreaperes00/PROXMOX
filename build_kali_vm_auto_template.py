#!/usr/bin/env python3
# build_kali_vm_auto_template.py

import os
import re
import subprocess
import requests
import argparse
import json
from bs4 import BeautifulSoup
from pathlib import Path

TEMPLATE_ID = 9000

def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄！")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

def id_in_use(vm_id: int) -> bool:
    vm_check = subprocess.run(["qm", "status", str(vm_id)],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    ct_check = subprocess.run(["pct", "status", str(vm_id)],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    return vm_check.returncode == 0 or ct_check.returncode == 0

def find_available_vm_id(start: int = 100):
    while True:
        if not id_in_use(start):
            return start
        start += 1

def get_disk_size_gb(vm_id: int, storage: str) -> str:
    result = subprocess.run(["qm", "config", str(vm_id)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True)
    for line in result.stdout.splitlines():
        if line.strip().startswith("scsi0:") and f"{storage}:" in line:
            parts = line.split(",")
            for p in parts:
                if p.strip().startswith("size="):
                    return p.split("=")[-1]
    return "未知"

def convert_to_gb(size_str: str) -> str:
    size_str = size_str.strip().upper()
    if size_str.endswith("G"):
        return size_str
    elif size_str.endswith("M"):
        size_in_mib = float(size_str[:-1])
        size_in_gb = size_in_mib / 1024
        return f"{size_in_gb:.1f}G"
    elif size_str.endswith("K"):
        size_in_kib = float(size_str[:-1])
        size_in_gb = size_in_kib / (1024 * 1024)
        return f"{size_in_gb:.2f}G"
    else:
        return size_str

def deploy_vm(args, vm_index=None):
    vm_id = find_available_vm_id(args.start_id or 100)
    name = args.name if vm_index is None else f"{args.name}-{vm_index+1}"
    desc = args.description if vm_index is None else f"{args.description} #{vm_index+1}"
    net_config = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net_config += f",tag={args.vlan}"

    if args.template_id:
        print(f"[INFO] 使用 Template VM (ID={args.template_id}) 快速複製 ...")
        subprocess.run(["qm", "clone", str(args.template_id), str(vm_id), "--name", name], check=True)
        subprocess.run(["qm", "set", str(vm_id),
                        "--memory", str(args.max_mem),
                        "--balloon", str(args.min_mem),
                        "--cores", str(args.cpu),
                        "--net0", net_config,
                        "--description", desc], check=True)
    else:
        print(f"[INFO] 建立 Kali VM 並轉為黃金映像 ...")

        working_dir = Path(args.workdir).resolve()
        working_dir.mkdir(parents=True, exist_ok=True)

        kali_dir, version, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
        iso_path = working_dir / filename

        if not iso_path.exists():
            print(f"[INFO] 清空目錄：{working_dir}")
            for f in working_dir.glob("*"):
                f.unlink()
            print(f"[INFO] 下載 Kali 映像：{kali_url}")
            subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5", "--show-progress", kali_url], check=True)
        else:
            print(f"[SKIP] 已存在 .7z：{filename}")

        qcow2file = next(working_dir.glob("*.qcow2"), None)
        if not qcow2file:
            print("[INFO] 解壓縮 Kali 映像 ...")
            subprocess.run(["unar", "-f", filename], check=True)
            print("[OK] 解壓縮完成")
        else:
            print(f"[SKIP] 偵測到已解壓的 .qcow2：{qcow2file.name}")

        os.chdir(working_dir)
        qcow2file = next(working_dir.glob("*.qcow2"), None)
        if not qcow2file:
            raise RuntimeError("找不到 qcow2 映像！")

        subprocess.run(["qm", "create", str(vm_id),
                        "--memory", str(args.max_mem),
                        "--balloon", str(args.min_mem),
                        "--cores", str(args.cpu),
                        "--name", name,
                        "--description", desc,
                        "--net0", net_config,
                        "--ostype", "l26",
                        "--autostart", "1",
                        "--startup", "order=10,up=30,down=30",
                        "--machine", "q35"], check=True)

        subprocess.run(["qm", "importdisk", str(vm_id), str(qcow2file), args.storage, "--format", "qcow2"], check=True)
        subprocess.run(["qm", "set", str(vm_id), "--scsi0", f"{args.storage}:vm-{vm_id}-disk-0"], check=True)
        subprocess.run(["qm", "resize", str(vm_id), "scsi0", args.resize], check=True)
        subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)

        if not Path("/dev/kvm").exists():
            subprocess.run(["qm", "set", str(vm_id), "--kvm", "0"], check=True)

        subprocess.run(["qm", "template", str(vm_id)], check=True)
        print(f"[OK] Template VM 已建立於 ID {vm_id}")

    subprocess.run(["qm", "start", str(vm_id)], check=True)

    vm_ip = "未知"
    try:
        result = subprocess.run(["qm", "guest", "cmd", str(vm_id), "network-get-interfaces"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and "ip-addresses" in result.stdout:
            data = json.loads(result.stdout)
            for interface in data:
                for ip in interface.get("ip-addresses", []):
                    if ip.get("ip-address-type") == "ipv4":
                        vm_ip = ip.get("ip-address")
                        break
    except Exception:
        pass

    disk_size = get_disk_size_gb(vm_id, args.storage)

    print(f"\n✅ Kali VM 建立完成")
    print(f"📌 VM 名稱：{name} (VM ID: {vm_id})")
    print(f"🧠 記憶體：{args.min_mem} ~ {args.max_mem} MB")
    print(f"🧮 CPU 核心數：{args.cpu}")
    print(f"🌐 網路：bridge={args.bridge}" + (f", vlan={args.vlan}" if args.vlan else ""))
    print(f"💾 磁碟大小：{convert_to_gb(disk_size)}")
    print(f"🌐 IP 位址：{vm_ip}")
    print(f"📂 儲存位置：{Path(args.workdir).resolve()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali VM 並自動化導入 Proxmox")
    parser.add_argument("--count", type=int, default=1, choices=range(1, 1001), metavar="[1-1000]", help="要建立的 VM 數量")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images", help="工作目錄")
    parser.add_argument("--start-id", type=int, help="起始 VM ID（預設自動分配）")
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

    template_conf = Path(f"/etc/pve/qemu-server/{TEMPLATE_ID}.conf")
    if template_conf.exists():
        print(f"[INFO] 偵測到 Template VM {TEMPLATE_ID}，將使用 clone 模式 ...")
        args.template_id = TEMPLATE_ID
    else:
        print(f"[INFO] 尚未存在 Template VM，將建立黃金映像 ...")
        args.template_id = None
        args.start_id = TEMPLATE_ID

    for i in range(args.count):
        deploy_vm(args, i)

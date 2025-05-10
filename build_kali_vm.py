#!/usr/bin/env python3
# build_kali_vm.py

import os
import re
import subprocess
import requests
import argparse
from bs4 import BeautifulSoup
from pathlib import Path

def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄！")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

def find_available_vm_id(start: int):
    while True:
        result = subprocess.run(["qm", "status", str(start)],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            return start
        start += 1

def main(args):
    base_url = "https://cdimage.kali.org/"
    working_dir = Path(args.workdir).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)

    kali_dir, version, filename, kali_url = get_latest_kali_url(base_url)
    iso_path = working_dir / filename

    skip_download = iso_path.exists()
    if not skip_download:
        for f in working_dir.glob("*"):
            f.unlink()

    vm_id = find_available_vm_id(args.start_id)

    subprocess.run(["apt-get", "update", "-y"], check=True)
    subprocess.run(["apt-get", "install", "-y", "unar", "wget", "curl"], check=True)

    os.chdir(working_dir)
    if not skip_download:
        subprocess.run(["wget", "-c", "--retry-connrefused", "--tries=5",
                        "--show-progress", kali_url], check=True)

    subprocess.run(["unar", "-f", filename], check=True)

    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        raise RuntimeError("找不到 qcow2 映像！")

    net_config = f"model=virtio,firewall=0,bridge={args.bridge}"
    if args.vlan:
        net_config += f",tag={args.vlan}"

    subprocess.run([
        "qm", "create", str(vm_id),
        "--memory", str(args.max_mem),
        "--balloon", str(args.min_mem),
        "--cores", str(args.cpu),
        "--name", args.name,
        "--description", args.description,
        "--net0", net_config,
        "--ostype", "l26",
        "--autostart", "1",
        "--startup", "order=10,up=30,down=30",
        "--machine", "q35"
    ], check=True)

    subprocess.run([
        "qm", "importdisk", str(vm_id), str(qcow2file), args.storage, "--format", "qcow2"
    ], check=True)
    subprocess.run([
        "qm", "set", str(vm_id), "--scsi0", f"{args.storage}:vm-{vm_id}-disk-0"
    ], check=True)
    subprocess.run([
        "qm", "resize", str(vm_id), "scsi0", args.resize
    ], check=True)

    subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)
    if not Path("/dev/kvm").exists():
        subprocess.run(["qm", "set", str(vm_id), "--kvm", "0"], check=True)

    subprocess.run(["qm", "start", str(vm_id)], check=True)

    print(f"\n✅ Kali VM 建立完成\nVM ID: {vm_id}\nDisk Resize: {args.resize}\nSaved in: {working_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立 Kali VM 並自動化導入 Proxmox")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images", help="工作目錄")
    parser.add_argument("--start-id", type=int, default=136, help="起始 VM ID")
    parser.add_argument("--name", default="kali-vm", help="VM 名稱")
    parser.add_argument("--description", default="Kali VM imported automatically", help="VM 說明")
    parser.add_argument("--min-mem", type=int, default=4096, help="最小記憶體")
    parser.add_argument("--max-mem", type=int, default=8192, help="最大記憶體")
    parser.add_argument("--cpu", type=int, default=4, help="CPU 核心數")
    parser.add_argument("--bridge", default="vmbr0", help="網路橋接")
    parser.add_argument("--vlan", type=str, help="VLAN ID")
    parser.add_argument("--resize", default="+20G", help="磁碟擴充大小")
    parser.add_argument("--storage", default="local-lvm", help="儲存目標名稱")
    args = parser.parse_args()
    main(args)

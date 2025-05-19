#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自動化建立 Kali Linux VM 腳本，加入 NLP 指令解析（OpenAI GPT）支援

import os
import re
import sys
import json
import time
import shutil
import subprocess
import argparse
import requests
import openai
from pathlib import Path

TEMPLATE_ID = 9000  # 固定的黃金映像 VM ID

# ========== 檢查 unar ==========
def ensure_unar_available():
    if shutil.which("unar") is not None:
        return  # OK
    print("[WARN] 系統缺少 unar，正在嘗試執行 setup_dependencies.py 自動修復...")
    setup_path = Path("/root/setup_dependencies.py")
    if not setup_path.exists():
        print("[ERROR] 找不到 /root/setup_dependencies.py，無法自動安裝 unar，請手動修復")
        sys.exit(1)
    try:
        subprocess.run(["python3", str(setup_path)], check=True)
    except subprocess.CalledProcessError:
        print("[ERROR] 嘗試執行 setup_dependencies.py 修復 unar 失敗，請手動檢查")
        sys.exit(1)
    if shutil.which("unar") is None:
        print("[ERROR] unar 套件仍未安裝成功，請手動安裝後重試")
        sys.exit(1)
    print("[OK] unar 安裝成功，繼續執行")

# ========== 自然語言轉 CLI 參數 ==========
def parse_nlp_to_args(nlp_instruction: str):
    prompt = f"""
將以下自然語言指令轉換為 JSON 格式參數，對應 CLI 指令中：
--count、--name、--description、--min-mem、--max-mem、--cpu、--bridge、--vlan、--resize、--storage

輸入：「{nlp_instruction}」

請輸出如下：
{{
  "count": 1,
  "name": ["kali-nlp"],
  "description": "Kali NLP VM",
  "min_mem": 4096,
  "max_mem": 8192,
  "cpu": 2,
  "bridge": "vmbr0",
  "vlan": null,
  "resize": "+0G",
  "storage": "local-lvm"
}}
只輸出純 JSON。
"""
    res = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "你是參數轉換助手，幫助將中文指令轉成 CLI 所需格式。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )
    result = json.loads(res['choices'][0]['message']['content'])
    defaults = {
        "count": 1,
        "name": ["kali-nlp"],
        "description": "Kali NLP VM",
        "min_mem": 4096,
        "max_mem": 8192,
        "cpu": 2,
        "bridge": "vmbr0",
        "vlan": None,
        "resize": "+0G",
        "storage": "local-lvm"
    }
    for key, val in defaults.items():
        result.setdefault(key, val)
    print("[INFO] 使用 NLP 轉換後參數：")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result

# ========== 從官網抓 Kali 最新版本 ==========
def get_latest_kali_url(base_url: str):
    response = requests.get(base_url)
    dirs = sorted(set(re.findall(r'kali-\d+\.\d+[a-z]?/', response.text)), reverse=True)
    if not dirs:
        raise RuntimeError("無法取得 Kali 最新版本目錄")
    kali_dir = dirs[0].strip('/')
    version = kali_dir.replace("kali-", "")
    filename = f"kali-linux-{version}-qemu-amd64.7z"
    return kali_dir, version, filename, f"{base_url}{kali_dir}/{filename}"

# ========== 建立模板 ==========
def create_template(args, version):
    vm_id = TEMPLATE_ID
    working_dir = Path(args.workdir).resolve()
    kali_dir, _, filename, kali_url = get_latest_kali_url("https://cdimage.kali.org/")
    iso_path = working_dir / filename
    version_file = working_dir / ".kali_version"

    working_dir.mkdir(parents=True, exist_ok=True)

    qcow2file = next(working_dir.glob("*.qcow2"), None)
    if not qcow2file:
        print(f"[INFO] 下載 Kali 映像：{kali_url}")
        subprocess.run(["wget", "-c", kali_url], check=True, cwd=working_dir)
        subprocess.run(["unar", "-f", filename], check=True, cwd=working_dir)
        qcow2file = next(working_dir.glob("*.qcow2"), None)
        if not qcow2file:
            raise RuntimeError("找不到解壓後的 qcow2 映像")

    if Path(f"/etc/pve/qemu-server/{vm_id}.conf").exists():
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
    subprocess.run(["qm", "importdisk", str(vm_id), str(qcow2file), args.storage], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--scsi0", f"{args.storage}:vm-{vm_id}-disk-0"], check=True)
    if args.resize != "+0G":
        subprocess.run(["qm", "resize", str(vm_id), "scsi0", args.resize], check=True)
    subprocess.run(["qm", "set", str(vm_id), "--boot", "order=scsi0", "--bootdisk", "scsi0"], check=True)
    subprocess.run(["qm", "template", str(vm_id)], check=True)

    with version_file.open("w") as vf:
        vf.write(version)

# ========== 複製 VM ==========
def deploy_vm(args, vm_name, index=None):
    vm_id = TEMPLATE_ID + index + 1
    desc = args.description if index is None else f"{args.description} #{index+1}"
    net = f"model=virtio,bridge={args.bridge}"
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

    return {
        "vm_id": vm_id,
        "name": vm_name,
        "cpu": args.cpu,
        "ram": f"{args.min_mem} ~ {args.max_mem} MB",
        "disk": "N/A",  # 可擴充
        "ip": "N/A"     # 可整合 guest-agent 查詢
    }

# ========== 主程式 ==========
if __name__ == "__main__":
    ensure_unar_available()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        key_file = Path("~/.openai_api_key").expanduser()
        if key_file.exists():
            with key_file.open() as f:
                api_key = f.read().strip()
        else:
            raise RuntimeError("[ERROR] NLP 模式需設定 OPENAI_API_KEY 環境變數或 ~/.openai_api_key")
    openai.api_key = api_key

    parser = argparse.ArgumentParser(description="建立 Kali Template 並快速複製多台 VM")
    parser.add_argument("--nlp", type=str, help="自然語言描述 VM 建立指令")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--name", nargs='+', default=["kali-vm"])
    parser.add_argument("--description", default="Kali VM auto-generated")
    parser.add_argument("--min-mem", type=int, default=4096)
    parser.add_argument("--max-mem", type=int, default=8192)
    parser.add_argument("--cpu", type=int, default=4)
    parser.add_argument("--bridge", default="vmbr0")
    parser.add_argument("--vlan", type=str)
    parser.add_argument("--resize", default="+0G")
    parser.add_argument("--storage", default="local-lvm")
    parser.add_argument("--workdir", default="/var/lib/vz/template/iso/kali-images")
    args = parser.parse_args()

    if args.nlp:
        parsed_args = parse_nlp_to_args(args.nlp)
        args.count = parsed_args.get("count", 1)
        args.name = parsed_args.get("name", ["kali-nlp"])
        args.description = parsed_args.get("description", "Kali NLP VM")
        args.min_mem = parsed_args.get("min_mem", 4096)
        args.max_mem = parsed_args.get("max_mem", 8192)
        args.cpu = parsed_args.get("cpu", 2)
        args.bridge = parsed_args.get("bridge", "vmbr0")
        args.vlan = parsed_args.get("vlan")
        args.resize = parsed_args.get("resize", "+0G")
        args.storage = parsed_args.get("storage", "local-lvm")

    if len(args.name) == 1:
        vm_names = [args.name[0]] + [f"{args.name[0]}-{i}" for i in range(1, args.count)]
    elif len(args.name) == args.count:
        vm_names = args.name
    else:
        raise ValueError(f"[ERROR] VM 名稱數量（{len(args.name)}）與 --count（{args.count}）不一致")

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
        print("[INFO] 偵測到需重新建立黃金映像 ...")
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

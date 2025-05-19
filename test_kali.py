#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 自動化建立 Kali Linux VM 腳本，加入 NLP 指令解析（OpenAI GPT）支援

import os
import re
import subprocess
import requests
import argparse
import json
import time
import shutil
from pathlib import Path
import openai

TEMPLATE_ID = 9000  # 固定的黃金映像 VM ID

# 讀取 API 金鑰：優先用環境變數，否則讀 ~/.openai_api_key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    key_file = Path("~/.openai_api_key").expanduser()
    if key_file.exists():
        with key_file.open() as f:
            api_key = f.read().strip()
    else:
        raise RuntimeError("[ERROR] NLP 模式需設定 OPENAI_API_KEY 環境變數或 ~/.openai_api_key")
openai.api_key = api_key

# ========== 自然語言轉 CLI 參數函式 ==========
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
  "max_mem": 4096,
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
    # fallback 預設
    defaults = {
        "count": 1,
        "name": ["kali-nlp"],
        "description": "Kali NLP VM",
        "min_mem": 4096,
        "max_mem": 4096,
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

# ========== 後續 function 可保留原始版本（略） ==========
# ensure_installed, get_latest_kali_url, create_template, deploy_vm, 等函式請與你原來的版本合併使用

# 主程式進入點
if __name__ == "__main__":
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
        args.max_mem = parsed_args.get("max_mem", 4096)
        args.cpu = parsed_args.get("cpu", 2)
        args.bridge = parsed_args.get("bridge", "vmbr0")
        args.vlan = parsed_args.get("vlan")
        args.resize = parsed_args.get("resize", "+0G")
        args.storage = parsed_args.get("storage", "local-lvm")

    if args.count < 1:
        raise ValueError("[ERROR] --count 必須大於等於 1")
    if args.min_mem < 512 or args.max_mem < args.min_mem:
        raise ValueError("[ERROR] 記憶體配置無效，請檢查 --min-mem 與 --max-mem")
    if args.cpu < 1:
        raise ValueError("[ERROR] --cpu 必須大於等於 1")
    if args.resize and not re.match(r"^[+-]?\d+[GMK]$", args.resize):
        raise ValueError("[ERROR] --resize 格式無效，請使用類似 +10G 的格式")
    if args.vlan and not args.vlan.isdigit():
        raise ValueError("[ERROR] --vlan 必須是數字")

    if len(args.name) == 1:
        vm_names = [args.name[0]] + [f"{args.name[0]}-{i}" for i in range(1, args.count)]
    elif len(args.name) == args.count:
        vm_names = args.name
    else:
        raise ValueError(f"[ERROR] VM 名稱數量（{len(args.name)}）與 --count（{args.count}）不一致")

    from auto_build_kali_vm import ensure_installed, get_latest_kali_url, create_template, deploy_vm

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

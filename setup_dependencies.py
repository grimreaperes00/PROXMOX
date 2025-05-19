#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Proxmox 每日自動更新與 Python 套件維護任務（全自動化）+ 日誌紀錄

import subprocess
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

def run_apt_upgrade():
    log("🔧 正在更新 Proxmox 主機套件 ...")
    subprocess.run(["apt", "update"], check=True, stdout=log_file, stderr=log_file)
    subprocess.run(["apt", "upgrade", "-y"], check=True, stdout=log_file, stderr=log_file)
    log("✅ 系統更新完成")

def ensure_apt_package(pkg_name):
    if shutil.which(pkg_name) is None:
        log(f"[INFO] 安裝系統套件: {pkg_name}")
        subprocess.run(["apt", "install", "-y", pkg_name], check=True, stdout=log_file, stderr=log_file)
    else:
        log(f"[OK] 系統套件 {pkg_name} 已安裝")

def ensure_pip_package(pkg_name):
    try:
        __import__(pkg_name)
        log(f"[OK] Python 模組 {pkg_name} 已存在")
    except ImportError:
        log(f"[INFO] 尚未安裝 Python 模組: {pkg_name}，執行安裝...")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg_name], check=True, stdout=log_file, stderr=log_file)

def upgrade_python_packages():
    log("📦 升級 pip 與核心 Python 套件 ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=True, stdout=log_file, stderr=log_file)
    packages = [
        "requests", "urllib3", "idna", "certifi", "setuptools", "wheel"
    ]
    for pkg in packages:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg], check=True, stdout=log_file, stderr=log_file)
    log("✅ Python 核心套件升級完成")
    # 額外記錄已安裝版本
    log("🔍 當前 Python 模組版本：")
    result = subprocess.run([sys.executable, "-m", "pip", "list"], stdout=subprocess.PIPE, text=True)
    with open(LOG_FILE, "a") as f:
        f.write(result.stdout)

if __name__ == "__main__":
    log_dir = Path("/root/update_log")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
    LOG_FILE = log_dir / log_name

    with open(LOG_FILE, "a") as log_file:
        run_apt_upgrade()
        ensure_apt_package("unar")
        upgrade_python_packages()
        ensure_pip_package("openai")
        ensure_pip_package("proxmoxer")
        ensure_pip_package("requests")

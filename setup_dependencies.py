#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 套件與系統依賴安裝器

import subprocess
import shutil
import sys

def ensure_apt_package(pkg_name):
    if shutil.which(pkg_name) is None:
        print(f"[INFO] 安裝系統套件: {pkg_name}")
        subprocess.run(["sudo", "apt", "update"], check=True)
        subprocess.run(["sudo", "apt", "install", "-y", pkg_name], check=True)
    else:
        print(f"[SKIP] 已安裝 {pkg_name}")

def ensure_pip_package(pkg_name):
    try:
        __import__(pkg_name)
        print(f"[SKIP] Python 模組 {pkg_name} 已存在")
    except ImportError:
        print(f"[INFO] 安裝 Python 套件: {pkg_name}")
        subprocess.run([sys.executable, "-m", "pip", "install", pkg_name], check=True)

if __name__ == "__main__":
    print("📦 安裝所有所需套件與依賴")

    # 系統依賴
    ensure_apt_package("unar")

    # Python 套件
    ensure_pip_package("openai")
    ensure_pip_package("proxmoxer")
    ensure_pip_package("requests")

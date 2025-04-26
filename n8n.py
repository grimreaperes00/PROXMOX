import subprocess
import argparse

# === 預設參數設定 ===
DEFAULT_CPU = 2
DEFAULT_RAM = 2048  # 單位：MB
DEFAULT_DISK = 10    # 單位：GB
DEFAULT_BRIDGE = "vmbr0"
DEFAULT_STORAGE = "local-lvm"
DEFAULT_TEMPLATE_ID = 9000  # 預設模板 VM ID


def run_command(cmd):
    """執行系統指令並顯示輸出"""
    print(f"\u26a1\ufe0f 執行指令: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def create_vm(vm_id, hostname, cpu=None, ram=None, disk=None, bridge=None, template_id=None):
    """建立新的 VM"""
    cpu = cpu or DEFAULT_CPU
    ram = ram or DEFAULT_RAM
    disk = disk or DEFAULT_DISK
    bridge = bridge or DEFAULT_BRIDGE
    template_id = template_id or DEFAULT_TEMPLATE_ID

    # Step 1: clone 從模板
    clone_cmd = [
        "qm", "clone", str(template_id), str(vm_id),
        "--name", hostname,
        "--full", "1",
        "--storage", DEFAULT_STORAGE
    ]
    run_command(clone_cmd)

    # Step 2: 設定 CPU / RAM / 磁碟 / 網卡
    set_cmd = [
        "qm", "set", str(vm_id),
        "--cores", str(cpu),
        "--memory", str(ram),
        "--net0", f"virtio,bridge={bridge}"
    ]
    run_command(set_cmd)

    # Step 3: 磁碟大小調整（可選）
    if disk:
        resize_cmd = [
            "qm", "resize", str(vm_id), "scsi0", f"{disk}G"
        ]
        run_command(resize_cmd)

    # Step 4: 啟動 VM
    start_cmd = ["qm", "start", str(vm_id)]
    run_command(start_cmd)

    print(f"\ud83c\udf89 VM {vm_id} ({hostname}) 建立完成並啟動！")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建立新的 Proxmox VM")
    parser.add_argument("--vm_id", required=True, help="要建立的 VM ID")
    parser.add_argument("--hostname", required=True, help="VM 主機名稱")
    parser.add_argument("--cpu", type=int, help="CPU核心數（可選）")
    parser.add_argument("--ram", type=int, help="記憶體MB（可選）")
    parser.add_argument("--disk", type=int, help="磁碟GB大小（可選）")
    parser.add_argument("--bridge", help="網卡橋接名稱（可選）")
    parser.add_argument("--template_id", type=int, help="模板 VM ID（可選）")

    args = parser.parse_args()

    create_vm(
        vm_id=args.vm_id,
        hostname=args.hostname,
        cpu=args.cpu,
        ram=args.ram,
        disk=args.disk,
        bridge=args.bridge,
        template_id=args.template_id
    )


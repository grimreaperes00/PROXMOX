- test_kali.sh 最基礎可作用新增KALI VM

- 參數資訊欄
```markdown
| 參數名稱            | 資料型別  | 預設值                                    | 說明                                                |
| --------------- | ----- | -------------------------------------- | ------------------------------------------------------------ |
| `--count`       | `int` | `1`                                    | 要建立的 VM 數量。支援批次建立。                               |
| `--workdir`     | `str` | `/var/lib/vz/template/iso/kali-images` | 工作目錄，下載與解壓 Kali QEMU 映像的位置。                     |
| `--name`        | `str` | `kali-vm`                              | VM 名稱（若為多台，將加上序號）。                                |
| `--description` | `str` | `Kali VM auto-generated`               | VM 描述欄位。                                                 |
| `--min-mem`     | `int` | `4096`（MB）                             | 最小記憶體，搭配 balloon 使用。                               |
| `--max-mem`     | `int` | `8192`（MB）                             | 最大記憶體。                                                 |
| `--cpu`         | `int` | `4`                                    | 分配給 VM 的虛擬 CPU 核心數量。                                |
| `--bridge`      | `str` | `vmbr0`                                | 網路橋接介面名稱（如 Proxmox 預設 `vmbr0`）。                    |
| `--vlan`        | `str` | `None`（選填）                             | 若有 VLAN tag，可指定如 `10`、`20` 等。                     |
| `--resize`      | `str` | `+20G`                                 | VM 磁碟擴充大小（基於 .qcow2 映像基礎上）。                       |
| `--storage`     | `str` | `local-lvm`                            | 儲存磁碟的 Proxmox storage 名稱，如 `local-lvm`、`ceph-ssd` 等。|

```
- 請先下載PYTHON套件
```
apt install python3-pip -y
```
- build_kali_vm_auto_template.py 當前最新KALI VM版本(參數如上)

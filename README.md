- test_kali.sh 最基礎可作用新增KALI VM無任何參數定義

- 請先下載PYTHON套件
```
apt install python3-pip -y
```
- build_kali_vm_auto_template.py 當前最新KALI VM版本(參數如下)

- 參數資訊欄
```markdown
| 參數名稱         | 預設值                                   | 資料型態 | 說明                               |
| --------------- | ---------------------------------------- | ---- | -------------------------------- |
| `--count`       | `1`                                      | int  | 要建立的 VM 數量                       |
| `--name`        | `["kali-vm"]`                            | list | VM 名稱（可為一個，或依 `--count` 提供多個）    |
| `--description` | `"Kali VM auto-generated"`               | str  | VM 描述資訊，會加上編號                    |
| `--min-mem`     | `4096`                                   | int  | VM 最小可用記憶體（單位 MB，ballooning 設定用） |
| `--max-mem`     | `8192`                                   | int  | VM 最大記憶體                         |
| `--cpu`         | `4`                                      | int  | VM CPU 核心數                       |
| `--bridge`      | `"vmbr0"`                                | str  | 網路橋接介面名稱（例如 vmbr0）               |
| `--vlan`        | `None`                                   | str  | 指定 VLAN tag（可選）                  |
| `--resize`      | `"+0G"`                                 | str  | 調整磁碟大小，會套用在 clone 出來的 VM 上       |
| `--storage`     | `"local-lvm"`                            | str  | 磁碟存放位置（Proxmox 的 storage 名稱）     |
| `--workdir`     | `"/var/lib/vz/template/iso/kali-images"` | str  | 映像與版本檢查所使用的工作資料夾                 |
```


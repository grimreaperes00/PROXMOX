- test_kali.sh 最基礎可作用新增KALI VM無任何參數定義

- 請先下載PYTHON套件
```
apt install python3-pip -y
```
- build_kali_vm_auto_template.py 當前最新KALI VM版本(參數如下)

- 參數資訊欄
```markdown
| 參數名稱         | 預設值         | 說明                                                                 |
|------------------|---------------|----------------------------------------------------------------------|
| `--count`        | `1`           | 要建立的 VM 數量，必須大於等於 1。                                   |
| `--name`         | `["kali-vm"]` | VM 名稱，支援單一名稱或多個名稱。                                    |
| `--description`  | `"Kali VM auto-generated"` | VM 的描述文字。                                                   |
| `--min-mem`      | `4096`        | VM 的最小記憶體大小（MB），必須大於等於 512 且小於等於 `--max-mem`。 |
| `--max-mem`      | `8192`        | VM 的最大記憶體大小（MB），必須大於等於 `--min-mem`。               |
| `--cpu`          | `4`           | VM 的 CPU 核心數量，必須大於等於 1。                                 |
| `--bridge`       | `"vmbr0"`     | VM 的網路橋接名稱。                                                 |
| `--vlan`         | 無            | VLAN 標籤，必須是數字（可選）。                                      |
| `--resize`       | `"+0G"`       | 磁碟大小調整值，例如 `+10G` 或 `+0G` 表示不變更，格式必須正確。      |
| `--storage`      | `"local-lvm"` | VM 的存儲位置。                                                     |
| `--workdir`      | `"/var/lib/vz/template/iso/kali-images"` | 工作目錄，用於存放下載的映像檔案。 |

```


# Any line starting with a "#" is a comment. 
# You do not need to type this in your shell.

#############
# VARIABLES #
#############

kali_url="https://cdimage.kali.org/kali-2024.4/kali-linux-2024.4-qemu-amd64.7z"
working_dir="/tmp/kali-download"
filename=$(
  echo "$kali_url" | 
  rev | awk -v FS='/' '{print $1}' | 
  rev
)
vm_id=136
vm_name="kali-vm"
vm_description="Kali VM imported from OffSec"
min_memory=4096
max_memory=8192
cpu_cores=4
os_type="l26"
# Uses local-lvm as this is the default on most PVE installations
# When in doubt, run `pvesm status --content images` and check which one you want to use
storage_target="local-lvm"
network_bridge="vmbr1"
vlan_id=666 # Leave blank if on default VLAN

################
# SANITY CHECK #
################

vm_id_used=$(
  find /etc/pve/nodes/ -type f -name '*.conf' | 
  grep qemu-server | 
  cut -d '/' -f 7 | 
  cut -d '.' -f 1 | 
  grep "$vm_id"
)

if [ -n "$vm_id_used" ] ; then
  echo -e "\n${vm_id} already taken. Please specify an unused id.\n"
  exit 1
fi

################
# DEPENDENCIES #
################

echo -e "\nUpdating apt packages and installaing 'unar' ...\n"
apt clean && apt update
apt install -y unar

#################
# CREATE THE VM #
#################

# Create the download directory
if ! [ -d "$working_dir" ]; then
  echo -e "\n${working_dir} does not exist. Creating ...\n"
  mkdir "$working_dir"
fi

cd "$working_dir"
echo -e "\nDownload Kali VM from ${kali_url} ... \n"
wget "$kali_url" 
echo -e "\nDownload completed. Extracting VM disk ... \n"
unar "$filename"

# Find the .qcow2 disk to import to the VM
qcow2file=$(find $PWD -name '*.qcow2')

# Create the Kali VM
if [ -z "$vlan_id" ] ; then
  net_config="model=virtio,firewall=0,bridge=${network_bridge}"
else
  net_config="model=virtio,firewall=0,bridge=${network_bridge},tag=${vlan_id}"
fi

echo -e "\nCreating the VM with specifications designated in variables ... \n"
qm create "$vm_id" --memory "$max_memory" --balloon "$min_memory" \
--cores "$cpu_cores" --name "$vm_name" --description "$vm_description" \
--net0 "$net_config" --ostype "$os_type" \
--autostart 1 --startup order=10,up=30,down=30

# Import the disk file to the VM. Wait for command to finish!
echo -e "\nImporting the .qcow2 disk ... \n"
qm importdisk "$vm_id" "$qcow2file" "$storage_target" --format qcow2

# Attach the disk to the VM
echo -e "\nAttaching the disk to the VM ... \n"
qm set "$vm_id" --scsi0 "${storage_target}:vm-${vm_id}-disk-0"

# Set the disk as the primary boot
echo -e "\nSetting the hard disk as the primary boot method ... \n"
qm set "$vm_id" --boot=order=scsi0

# Start the VM
echo -e "\nAll done. Starting VM with ID: ${vm_id} and cleaning up ... \n"
qm start "$vm_id"

# Clean up
cd "$HOME"
rm -rf "$working_dir"

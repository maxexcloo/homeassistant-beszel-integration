"""Constants for the Beszel integration."""

from homeassistant.const import Platform

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 1
DOMAIN = "beszel"
MANUFACTURER = "Beszel"
PLATFORMS = [Platform.SENSOR]

# Beszel OS type codes mapped to display names and icons
OPERATING_SYSTEMS = {
    0: ("Linux", "mdi:linux"),
    1: ("Darwin (macOS)", "mdi:apple"),
    2: ("Windows", "mdi:microsoft-windows"),
    3: ("FreeBSD", "mdi:freebsd"),
}

# Beszel SystemInfo fields
ATTR_AGENT_VERSION = "v"
ATTR_CORES = "c"
ATTR_CPU_MODEL = "m"
ATTR_KERNEL_VERSION = "k"
ATTR_OS = "os"
ATTR_THREADS = "t"
ATTR_UPTIME = "u"

# Beszel SystemStats fields
ATTR_BANDWIDTH = "b"
ATTR_BATTERY = "bat"
ATTR_CPU_PERCENT = "cpu"
ATTR_DISK_IO = "dio"
ATTR_DISK_IO_STATS = "dios"
ATTR_DISK_PERCENT = "dp"
ATTR_DISK_READ_PS_MB = "dr"
ATTR_DISK_TOTAL_GB = "d"
ATTR_DISK_USED_GB = "du"
ATTR_DISK_WRITE_PS_MB = "dw"
ATTR_EXTRA_FS = "efs"
ATTR_GPU_DATA = "g"
ATTR_MEM_BUFF_CACHE_GB = "mb"
ATTR_MEM_PERCENT = "mp"
ATTR_MEM_TOTAL_GB = "m"
ATTR_MEM_USED_GB = "mu"
ATTR_MEM_ZFS_ARC_GB = "mz"
ATTR_NET_RECV_PS_MB = "nr"
ATTR_NET_SENT_PS_MB = "ns"
ATTR_SWAP_PERCENT = "sp"
ATTR_SWAP_TOTAL_GB = "s"
ATTR_SWAP_USED_GB = "su"
ATTR_TEMPERATURES = "t"

# Beszel ExtraFsStats fields
ATTR_FS_DISK_IO_STATS = "dios"
ATTR_FS_DISK_PERCENT = "dp"
ATTR_FS_DISK_READ_BYTES = "rb"
ATTR_FS_DISK_READ_PS_MB = "r"
ATTR_FS_DISK_TOTAL_GB = "d"
ATTR_FS_DISK_USED_GB = "du"
ATTR_FS_DISK_WRITE_BYTES = "wb"
ATTR_FS_DISK_WRITE_PS_MB = "w"

# Beszel GPUData fields
ATTR_GPU_MEM_TOTAL_MB = "mt"
ATTR_GPU_MEM_USED_MB = "mu"
ATTR_GPU_NAME = "n"
ATTR_GPU_POWER_PACKAGE_W = "pp"
ATTR_GPU_POWER_W = "p"
ATTR_GPU_USAGE_PERCENT = "u"

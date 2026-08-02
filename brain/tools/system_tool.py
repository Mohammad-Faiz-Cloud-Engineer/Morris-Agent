"""Portable system-status tool for Windows, macOS, and Linux."""

import platform
import time
from pathlib import Path

try:
    import psutil
except ImportError:  # A useful response is still possible without psutil.
    psutil = None


def get_system_status() -> str:
    """Return platform, memory, uptime, storage, and available temperature data."""
    parts = [f"I'm running on {platform.system()} {platform.release()}"]
    if psutil is None:
        return ". ".join(parts) + ". Install psutil for detailed system status."

    memory = psutil.virtual_memory()
    parts.append(f"I'm using {(memory.used / 2**30):.1f} of {(memory.total / 2**30):.1f} gigabytes of RAM")

    uptime_seconds = max(0, time.time() - psutil.boot_time())
    days, remainder = divmod(int(uptime_seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        parts.append(f"the system has been up for {days} days and {hours} hours")
    elif hours:
        parts.append(f"the system has been up for {hours} hours and {minutes} minutes")
    else:
        parts.append(f"the system has been up for {minutes} minutes")

    disk = psutil.disk_usage(Path.home().anchor)
    parts.append(f"disk usage is {(disk.used / 2**30):.0f} of {(disk.total / 2**30):.0f} gigabytes")

    # Sensors are exposed on most Linux machines; Windows and macOS typically
    # do not permit a normal process to read CPU temperature, so omit it there.
    try:
        temperatures = psutil.sensors_temperatures()
        readings = [entry.current for entries in temperatures.values() for entry in entries if entry.current]
        if readings:
            parts.append(f"the reported CPU temperature is {max(readings):.0f} degrees Celsius")
    except (AttributeError, OSError):
        pass

    return ". ".join(parts) + "."

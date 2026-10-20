import sys

if sys.platform == "win32":
    from .windows import data_directory, lock_instance, set_autostart
elif sys.platform == "linux":
    from .linux import data_directory, lock_instance, set_autostart
else:
    raise RuntimeError("GaddHub currently supports Windows and Linux only.")

__all__ = ["data_directory", "lock_instance", "set_autostart"]

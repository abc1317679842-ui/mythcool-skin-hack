# Notices

## Scope of operation

This project operates on a **running process's memory only**.

It does not copy, modify, decompile or redistribute any file, binary, firmware,
asset or source code belonging to Myth.Cool / Valkyrie (金钟宝智能科技) or any
other vendor. No vendor code is included in this repository.

The patch is applied at runtime, lives entirely in memory, and disappears as
soon as the target application restarts. Removing the scheduled task and the
install directory leaves the system exactly as it was.

## Trademarks

"Valkyrie", "Myth.Cool" and other product names are used **descriptively**, solely
to indicate compatibility (nominative / referential use). No vendor logos are used.

This is **not an official product** and is neither affiliated with nor endorsed by
those vendors.

## Third-party components

The installer creates a private Python virtual environment and installs
[**frida**](https://github.com/frida/frida) from PyPI (wxWindows Library Licence).
frida itself is not redistributed in this repository.

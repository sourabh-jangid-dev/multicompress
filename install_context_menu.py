"""
install_context_menu.py
------------------------
Adds (or removes) a Windows Explorer right-click menu entry:
    "Compress with MultiCompress"
so you can right-click any file → compress it. Makes the app feel installed.

USAGE:
    python install_context_menu.py            # install
    python install_context_menu.py --remove   # uninstall

HOW IT WORKS (teaching):
  Windows reads context-menu entries from the registry. For "any file" the key
  is  HKEY_CURRENT_USER\\Software\\Classes\\*\\shell\\<Name>. We write a command
  there that launches our app with the clicked file path ("%1") as an argument.
  We use HKCU (current user) so NO admin rights are required.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

MENU_NAME = "MultiCompress"
MENU_LABEL = "Compress with MultiCompress"

PROJECT_ROOT = Path(__file__).resolve().parent
ICON_PATH = PROJECT_ROOT / "docs" / "icon.ico"

# Base registry path: '*' means "all file types".
KEY_PATH = rf"Software\Classes\*\shell\{MENU_NAME}"
COMMAND_KEY_PATH = KEY_PATH + r"\command"


def _launch_command() -> str:
    """
    Build the command Windows runs when the menu item is clicked.

    Prefer the built .exe (dist/MultiCompress/MultiCompress.exe) if present;
    otherwise fall back to running main.py with pythonw (no console flash).
    The trailing "%1" is the file the user right-clicked.
    """
    exe = PROJECT_ROOT / "dist" / "MultiCompress" / "MultiCompress.exe"
    if exe.exists():
        return f'"{exe}" "%1"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{runner}" "{PROJECT_ROOT / "main.py"}" "%1"'


def install():
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, MENU_LABEL)
        if ICON_PATH.exists():
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, str(ICON_PATH))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, COMMAND_KEY_PATH) as ck:
        winreg.SetValueEx(ck, "", 0, winreg.REG_SZ, _launch_command())
    print(f'Installed: right-click any file -> "{MENU_LABEL}"')
    print(f"Command: {_launch_command()}")


def remove():
    # Delete child key first, then the parent (registry requires this order).
    for path in (COMMAND_KEY_PATH, KEY_PATH):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass
    print("Removed the right-click menu entry.")


if __name__ == "__main__":
    if "--remove" in sys.argv:
        remove()
    else:
        install()

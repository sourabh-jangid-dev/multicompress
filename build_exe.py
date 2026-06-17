"""
build_exe.py — bundle the app into a standalone Windows application.

Run:  python build_exe.py

WHAT THIS DOES (teaching):
  PyInstaller reads our code, finds every import, and packs Python itself +
  all libraries + the FFmpeg binary into a self-contained folder. The end user
  double-clicks MultiCompress.exe — they do NOT need Python installed.

  The `--collect-all` flags are important: customtkinter, tkinterdnd2 and
  imageio-ffmpeg ship DATA files (themes, the tkdnd library, the ffmpeg.exe)
  that PyInstaller won't grab automatically. collect-all forces them in.
"""

import os
import sys

import PyInstaller.__main__

# --add-data uses ';' on Windows and ':' on macOS/Linux. os.pathsep handles both,
# so this same script builds a .exe on Windows and a .app/binary on macOS/Linux.
SEP = os.pathsep

args = [
    "main.py",
    "--name=MultiCompress",
    "--windowed",                 # GUI app -> no console window
    "--noconfirm",                # overwrite previous build without asking
    "--clean",
    "--paths=src",                # so PyInstaller finds our 'gui' & 'compressor' packages
    # Bundle the data/binaries these packages ship with:
    "--collect-all=customtkinter",
    "--collect-all=tkinterdnd2",
    "--collect-all=imageio_ffmpeg",
    "--collect-all=pillow_heif",   # HEIC support data/binaries
    # Bundle BOTH icons so the running window can load the right one per-OS.
    f"--add-data=docs/icon.ico{SEP}docs",
    f"--add-data=docs/icon.png{SEP}docs",
]

# The .exe's own icon: Windows uses .ico. (On macOS PyInstaller wants .icns,
# so we skip it there rather than fail.)
if sys.platform.startswith("win"):
    args.append("--icon=docs/icon.ico")

PyInstaller.__main__.run(args)

print("\nBuild complete. Your app is in:  dist/MultiCompress/")
print("Run dist/MultiCompress/MultiCompress.exe to test it.")
print("Zip the dist/MultiCompress folder and attach it to a GitHub Release.")

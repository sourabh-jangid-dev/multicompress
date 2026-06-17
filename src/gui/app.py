"""
gui/app.py
----------
The desktop window (CustomTkinter). Handles SCREEN + INPUT only; all real work
goes through compressor.engine.compress_path().

Features:
  • Drag & drop files onto the window (tkinterdnd2)
  • 5 presets + an Advanced mode with manual sliders
  • Background-thread compression with live per-file progress
  • Stop button (cancels mid-job)
  • Open-output-folder, light/dark toggle, remembered settings, lifetime stats

THREADING: compression runs on a worker thread; UI updates are pushed back to
the main thread with self.after(0, fn) because Tkinter isn't thread-safe.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_OK = True
except Exception:
    _DND_OK = False

from compressor import config, history
from compressor.engine import compress_path, detect_kind, estimate_reduction
from compressor.presets import DEFAULT_PRESET, PRESETS, make_custom_preset
from compressor.utils import file_size, human_size, open_in_file_manager, resource_path


class CompressorApp(ctk.CTk):
    def __init__(self, initial_files: list[str] | None = None):
        super().__init__()

        # Load saved settings (preset, output folder, theme).
        self.settings = config.load_settings()
        ctk.set_appearance_mode(self.settings.get("theme", "dark"))
        ctk.set_default_color_theme("blue")

        # Enable drag-and-drop on this window if the library loaded.
        if _DND_OK:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
            except Exception:
                pass

        self.title("MultiCompress — Video / Image / Audio / PDF / Files")
        self.geometry("860x720")
        self.minsize(760, 620)

        # App icon in the title bar / taskbar — cross-platform.
        # Windows uses .ico via iconbitmap; macOS/Linux use a PNG via iconphoto.
        try:
            if sys.platform.startswith("win"):
                ico = resource_path("docs/icon.ico")
                if ico.exists():
                    self.iconbitmap(str(ico))
            else:
                png = resource_path("docs/icon.png")
                if png.exists():
                    self._icon_img = tkinter.PhotoImage(file=str(png))
                    self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        # --- State ----------------------------------------------------
        self.files: list[str] = []
        self.output_dir: str = self.settings.get("output_dir")
        self.preset_key: str = self.settings.get("preset", DEFAULT_PRESET)
        self.is_running = False
        self.advanced = False
        self.cancel_event = threading.Event()
        self.row_widgets: dict[str, dict] = {}

        self._build_ui()
        self._register_dnd()
        self.protocol("WM_DELETE_WINDOW", self._on_close)  # save settings on exit

        # Files passed on the command line (e.g. from the Explorer right-click
        # menu) get pre-loaded into the queue on startup.
        for p in (initial_files or []):
            if p and p not in self.files and os.path.exists(p):
                self.files.append(p)
                self._add_file_row(p)
        if initial_files:
            self._refresh_status()

    # ==================================================================
    #  UI LAYOUT
    # ==================================================================
    def _build_ui(self):
        # ---- Header + theme toggle ----
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(top, text="🗜️  MultiCompress",
                     font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        self.theme_switch = ctk.CTkSwitch(top, text="Light",
                                          command=self._toggle_theme)
        self.theme_switch.pack(side="right")
        if self.settings.get("theme") == "light":
            self.theme_switch.select()
        ctk.CTkLabel(self, text="Compress videos, images, audio, PDFs & files — 100% offline",
                     text_color="gray").pack()

        # ---- Lifetime stats line ----
        self.stats_label = ctk.CTkLabel(self, text=self._stats_text(), text_color="#3b8ed0")
        self.stats_label.pack(pady=(2, 6))

        # ---- Controls: preset + advanced toggle ----
        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(controls, text="Preset:").grid(row=0, column=0, padx=8, pady=8)
        self._preset_names = {p.name: key for key, p in PRESETS.items()}
        self.preset_menu = ctk.CTkOptionMenu(
            controls, values=list(self._preset_names.keys()),
            command=self._on_preset_change, width=230)
        self.preset_menu.set(PRESETS[self.preset_key].name)
        self.preset_menu.grid(row=0, column=1, padx=8)
        self.adv_switch = ctk.CTkSwitch(controls, text="Advanced (manual)",
                                        command=self._toggle_advanced)
        self.adv_switch.grid(row=0, column=2, padx=16)

        # Parallel jobs: how many files to compress at once. Default is a sensible
        # auto value based on CPU cores. More = faster batches on multi-core CPUs.
        ctk.CTkLabel(controls, text="Parallel:").grid(row=0, column=3, padx=(8, 0))
        cores = os.cpu_count() or 2
        self._auto_workers = max(1, min(4, cores - 1))
        self.parallel_menu = ctk.CTkOptionMenu(
            controls, width=90,
            values=["Auto", "1", "2", "3", "4"])
        self.parallel_menu.set(self.settings.get("parallel", "Auto"))
        self.parallel_menu.grid(row=0, column=4, padx=8)

        # ---- Target-size mode: compress to land under a chosen size ----
        self.target_switch = ctk.CTkSwitch(controls, text="Target size:",
                                           command=self._toggle_target)
        self.target_switch.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")
        self.target_entry = ctk.CTkEntry(controls, width=80, placeholder_text="500")
        self.target_entry.grid(row=1, column=1, padx=4, pady=(0, 8), sticky="w")
        self.target_entry.configure(state="disabled")
        # Unit: KB (e.g. govt portals: photo <50 KB) or MB (e.g. email <25 MB).
        self.unit_menu = ctk.CTkOptionMenu(controls, width=70, values=["KB", "MB"])
        self.unit_menu.set(self.settings.get("target_unit", "MB"))
        self.unit_menu.grid(row=1, column=2, padx=4, pady=(0, 8), sticky="w")
        ctk.CTkLabel(controls, text="(video/image/audio/pdf)", text_color="gray")\
            .grid(row=1, column=3, columnspan=2, padx=4, sticky="w")

        # ---- Advanced sliders (hidden until toggled) ----
        self.adv_frame = ctk.CTkFrame(self)
        self._build_advanced(self.adv_frame)

        # ---- Output folder row ----
        outrow = ctk.CTkFrame(self)
        outrow.pack(fill="x", padx=16, pady=6)
        ctk.CTkButton(outrow, text="📁 Output Folder…", width=150,
                      command=self._choose_output).pack(side="left", padx=8, pady=8)
        self.output_label = ctk.CTkLabel(outrow, text=self._short(self.output_dir),
                                         text_color="gray")
        self.output_label.pack(side="left", padx=8)
        ctk.CTkButton(outrow, text="Open ↗", width=70, fg_color="gray30",
                      command=self._open_output).pack(side="right", padx=8)

        # ---- File buttons ----
        btns = ctk.CTkFrame(self)
        btns.pack(fill="x", padx=16)
        ctk.CTkButton(btns, text="➕  Add Files",
                      command=self._add_files).pack(side="left", padx=6, pady=8)
        ctk.CTkButton(btns, text="🗑  Clear", fg_color="gray30",
                      command=self._clear_files).pack(side="left", padx=6)
        hint = "  …or drag & drop files here" if _DND_OK else ""
        ctk.CTkLabel(btns, text=hint, text_color="gray").pack(side="left", padx=8)

        # ---- File list ----
        self.file_frame = ctk.CTkScrollableFrame(self, label_text="Files to compress")
        self.file_frame.pack(fill="both", expand=True, padx=16, pady=10)

        # ---- Bottom: compress + stop + status ----
        bottom = ctk.CTkFrame(self)
        bottom.pack(fill="x", padx=16, pady=(0, 14))
        brow = ctk.CTkFrame(bottom, fg_color="transparent")
        brow.pack(fill="x")
        self.compress_btn = ctk.CTkButton(
            brow, text="🚀  Compress All", height=44,
            font=ctk.CTkFont(size=16, weight="bold"), command=self._start)
        self.compress_btn.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=8)
        self.stop_btn = ctk.CTkButton(
            brow, text="⏹ Stop", height=44, width=110, fg_color="#b03030",
            hover_color="#902020", state="disabled", command=self._stop)
        self.stop_btn.pack(side="left", padx=(4, 8))
        self.status_label = ctk.CTkLabel(bottom, text="Add some files to begin.",
                                         text_color="gray")
        self.status_label.pack()

    def _build_advanced(self, parent):
        """Manual sliders for power users. Values feed make_custom_preset()."""
        def slider_row(r, label, frm, to, default, fmt=lambda v: str(int(v))):
            ctk.CTkLabel(parent, text=label, width=160, anchor="w")\
                .grid(row=r, column=0, padx=10, pady=6, sticky="w")
            val = ctk.CTkLabel(parent, text=fmt(default), width=60)
            val.grid(row=r, column=2, padx=8)
            s = ctk.CTkSlider(parent, from_=frm, to=to, width=320,
                              command=lambda v, lbl=val, f=fmt: lbl.configure(text=f(v)))
            s.set(default)
            s.grid(row=r, column=1, padx=8)
            return s

        self.s_quality = slider_row(0, "Image quality", 10, 100, 80)
        self.s_crf = slider_row(1, "Video CRF (lower=better)", 18, 35, 24)
        self.s_height = slider_row(2, "Max video height (px)", 360, 2160, 1080)
        self.s_abitrate = slider_row(3, "Audio bitrate (kbps)", 64, 256, 128)

    # ==================================================================
    #  DRAG & DROP
    # ==================================================================
    def _register_dnd(self):
        if not _DND_OK:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            pass

    def _on_drop(self, event):
        # event.data is a Tcl list string; splitlist handles braces/spaces.
        for raw in self.tk.splitlist(event.data):
            p = raw.strip()
            if p and p not in self.files and os.path.exists(p):
                self.files.append(p)
                self._add_file_row(p)
        self._refresh_status()

    # ==================================================================
    #  USER ACTIONS
    # ==================================================================
    def _on_preset_change(self, friendly_name: str):
        self.preset_key = self._preset_names[friendly_name]

    def _toggle_advanced(self):
        self.advanced = bool(self.adv_switch.get())
        if self.advanced:
            self.adv_frame.pack(fill="x", padx=16, pady=4,
                                after=self.preset_menu.master)
            self.preset_menu.configure(state="disabled")
        else:
            self.adv_frame.pack_forget()
            self.preset_menu.configure(state="normal")

    def _toggle_target(self):
        on = bool(self.target_switch.get())
        self.target_entry.configure(state="normal" if on else "disabled")

    def _target_mb(self) -> float | None:
        """
        Return the target size in MB if target mode is on and valid, else None.
        Converts from the selected unit (KB or MB) — KB matters for things like
        government portals that require a photo under 50 KB.
        """
        if not self.target_switch.get():
            return None
        try:
            value = float(self.target_entry.get())
            if value <= 0:
                return None
            return value / 1024 if self.unit_menu.get() == "KB" else value
        except (ValueError, TypeError):
            return None

    def _toggle_theme(self):
        theme = "light" if self.theme_switch.get() else "dark"
        ctk.set_appearance_mode(theme)
        self.settings["theme"] = theme

    def _choose_output(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir)
        if folder:
            self.output_dir = folder
            self.output_label.configure(text=self._short(folder))

    def _open_output(self):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        open_in_file_manager(self.output_dir)   # cross-platform

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select files to compress",
            filetypes=[
                ("All supported", "*.mp4 *.mov *.avi *.mkv *.webm *.jpg *.jpeg *.png "
                                  "*.webp *.bmp *.tiff *.gif *.pdf *.mp3 *.wav *.m4a *.flac"),
                ("Videos", "*.mp4 *.mov *.avi *.mkv *.webm *.wmv *.m4v"),
                ("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.gif"),
                ("Audio", "*.mp3 *.wav *.m4a *.flac *.aac *.ogg"),
                ("PDF", "*.pdf"),
                ("All files", "*.*"),
            ])
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                self._add_file_row(p)
        self._refresh_status()

    def _clear_files(self):
        if self.is_running:
            return
        self.files.clear()
        for child in self.file_frame.winfo_children():
            child.destroy()
        self.row_widgets.clear()
        self._refresh_status()

    def _add_file_row(self, path: str):
        row = ctk.CTkFrame(self.file_frame)
        row.pack(fill="x", pady=3)
        kind = detect_kind(path)
        icon = {"video": "🎬", "image": "🖼️", "audio": "🎵",
                "pdf": "📄", "archive": "📦"}.get(kind, "📦")
        ctk.CTkLabel(row, text=f"{icon} {Path(path).name}", anchor="w",
                     width=250).pack(side="left", padx=8)
        ctk.CTkLabel(row, text=human_size(file_size(path)), width=70,
                     text_color="gray").pack(side="left")
        # Estimated reduction hint (honest range, shown before compressing).
        ctk.CTkLabel(row, text=estimate_reduction(path), width=80,
                     text_color="#6b7fa0").pack(side="left")
        bar = ctk.CTkProgressBar(row, width=140)
        bar.set(0)
        bar.pack(side="left", padx=8)
        result_lbl = ctk.CTkLabel(row, text="queued", width=110, text_color="gray")
        result_lbl.pack(side="left", padx=8)
        self.row_widgets[path] = {"bar": bar, "result": result_lbl, "row": row}

    # ==================================================================
    #  COMPRESSION (worker thread)
    # ==================================================================
    def _resolve_preset(self):
        """Return either a preset key (str) or a custom Preset from sliders."""
        if self.advanced:
            return make_custom_preset(
                image_quality=int(self.s_quality.get()),
                image_max_dim=int(self.s_height.get()),   # reuse height as image cap
                video_crf=int(self.s_crf.get()),
                video_max_height=int(self.s_height.get()),
                audio_bitrate=int(self.s_abitrate.get()),
            )
        return self.preset_key

    def _worker_count(self) -> int:
        """How many files to compress at once (from the Parallel selector)."""
        choice = self.parallel_menu.get()
        if choice == "Auto":
            return self._auto_workers
        try:
            return max(1, int(choice))
        except ValueError:
            return 1

    def _start(self):
        if self.is_running or not self.files:
            return
        self.is_running = True
        self.cancel_event.clear()
        self.compress_btn.configure(state="disabled", text="Compressing…")
        self.stop_btn.configure(state="normal")
        preset = self._resolve_preset()
        target = self._target_mb()
        threading.Thread(target=self._run_batch, args=(preset, target),
                         daemon=True).start()

    def _stop(self):
        # Signal all workers + FFmpeg processes to stop ASAP.
        self.cancel_event.set()
        self.status_label.configure(text="Stopping…", text_color="orange")

    def _compress_one(self, path, preset, target_mb) -> dict:
        """
        Compress a SINGLE file. Runs inside a thread-pool worker.

        Why threads work here despite Python's GIL: the heavy lifting happens in
        FFmpeg (a separate process) and in Pillow/PyMuPDF (C extensions that
        release the GIL). So multiple files genuinely compress in parallel.
        """
        if self.cancel_event.is_set():
            return {"input": path, "cancelled": True, "success": False,
                    "original_bytes": 0, "compressed_bytes": 0}

        self._ui(lambda: self.row_widgets[path]["result"].configure(
            text="working…", text_color="orange"))

        def cb(pct):
            self._ui(lambda: self.row_widgets[path]["bar"].set(pct / 100.0))

        result = compress_path(path, self.output_dir, preset, cb,
                               self.cancel_event, target_mb=target_mb)
        self._update_row(path, result)
        return result

    def _update_row(self, path, result):
        """Update one row's result label + progress bar (called via the UI thread)."""
        if result.get("cancelled"):
            self._ui(lambda: self.row_widgets[path]["result"]
                     .configure(text="cancelled", text_color="orange"))
            return
        if result.get("success"):
            note = result.get("note", "")
            if note and result.get("saved_percent", 0) <= 0.5:
                txt = f"✓ {note}"[:20]      # e.g. "already under target"
            else:
                txt = f"✓ -{result['saved_percent']}%"
            color = "#33cc66"
            self._ui(lambda: self._add_preview_button(path, result))
        else:
            # Show the real reason (e.g. "file is locked"), not just "failed".
            reason = result.get("error", "failed")
            txt, color = f"✗ {reason}"[:18], "#ff5555"
        self._ui(lambda: self.row_widgets[path]["result"].configure(text=txt, text_color=color))
        self._ui(lambda: self.row_widgets[path]["bar"].set(1.0))

    def _add_preview_button(self, path, result):
        """Add a 👁 button to a finished IMAGE row to compare before/after."""
        if detect_kind(path) != "image":
            return
        widgets = self.row_widgets.get(path)
        if not widgets or widgets.get("preview_added"):
            return
        widgets["preview_added"] = True
        out = result.get("output", "")
        btn = ctk.CTkButton(widgets["row"], text="👁", width=34, fg_color="gray30",
                            command=lambda: self._show_preview(path, out))
        btn.pack(side="left", padx=4)

    def _show_preview(self, original: str, compressed: str):
        """Pop up a window comparing the original and compressed image."""
        win = ctk.CTkToplevel(self)
        win.title("Before / After")
        win.geometry("780x480")
        win.after(150, win.lift)
        win._imgs = []  # keep references so images aren't garbage-collected

        def panel(parent, label, img_path, side):
            frame = ctk.CTkFrame(parent)
            frame.pack(side=side, fill="both", expand=True, padx=10, pady=10)
            try:
                im = Image.open(img_path)
                im.thumbnail((340, 340), Image.LANCZOS)
                cimg = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
                win._imgs.append(cimg)
                ctk.CTkLabel(frame, image=cimg, text="").pack(pady=8)
            except Exception:
                ctk.CTkLabel(frame, text="(preview unavailable)").pack(pady=40)
            ctk.CTkLabel(frame, text=f"{label}\n{human_size(file_size(img_path))}",
                         font=ctk.CTkFont(size=14, weight="bold")).pack()

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True)
        panel(body, "Original", original, "left")
        panel(body, "Compressed", compressed, "right")

    def _run_batch(self, preset, target_mb=None):
        total_before = total_after = 0
        ok = 0
        workers = self._worker_count()

        # ThreadPoolExecutor runs up to `workers` _compress_one calls at once.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._compress_one, p, preset, target_mb): p
                       for p in list(self.files)}
            for fut in as_completed(futures):
                result = fut.result()
                if result.get("cancelled"):
                    continue
                total_before += result.get("original_bytes", 0)
                total_after += result.get("compressed_bytes", 0)
                if result.get("success"):
                    ok += 1

        saved = total_before - total_after
        pct = (saved / total_before * 100) if total_before else 0
        cancelled = self.cancel_event.is_set()
        msg = ("Stopped. " if cancelled else "Done. ") + \
              f"{ok}/{len(self.files)} files · Saved {human_size(saved)} ({pct:.1f}%) " \
              f"· {workers}× parallel · → {self.output_dir}"
        self._ui(lambda: self.status_label.configure(
            text=msg, text_color="orange" if cancelled else "#33cc66"))
        self._ui(lambda: self.stats_label.configure(text=self._stats_text()))
        self._ui(self._finish)

    def _finish(self):
        self.is_running = False
        self.compress_btn.configure(state="normal", text="🚀  Compress All")
        self.stop_btn.configure(state="disabled")

    # ==================================================================
    #  HELPERS
    # ==================================================================
    def _ui(self, fn):
        self.after(0, fn)

    def _stats_text(self) -> str:
        s = history.lifetime_stats()
        if s["files"] == 0:
            return "Lifetime: nothing compressed yet — let's change that 🚀"
        return f"Lifetime: {s['files']} files · {human_size(s['saved_bytes'])} saved 🎉"

    def _refresh_status(self):
        n = len(self.files)
        total = human_size(sum(file_size(f) for f in self.files))
        self.status_label.configure(
            text=(f"{n} file(s) queued — {total} total" if n else "Add some files to begin."),
            text_color="gray")

    def _on_close(self):
        self.settings.update({"preset": self.preset_key, "output_dir": self.output_dir,
                              "parallel": self.parallel_menu.get(),
                              "target_unit": self.unit_menu.get()})
        config.save_settings(self.settings)
        self.destroy()

    @staticmethod
    def _short(path: str, maxlen: int = 42) -> str:
        return path if len(path) <= maxlen else "…" + path[-maxlen:]


def run(initial_files: list[str] | None = None):
    CompressorApp(initial_files=initial_files).mainloop()

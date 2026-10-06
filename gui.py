"""
Ruvex - Modern Graphical User Interface (GUI) for RAW to PNG, WEBP & JPEG Converter.
Built with CustomTkinter for a sleek dark/light mode desktop experience.
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

from core.constants import (
    SUPPORTED_RAW_EXTENSIONS,
    SUPPORTED_FORMATS_BY_BRAND,
    OUTPUT_FORMATS,
    SCALE_OPTIONS,
    COLOR_SPACES,
    DEMOSAIC_ALGORITHMS,
    WHITE_BALANCE_MODES,
    BIT_DEPTH_OPTIONS,
    JPEG_QUALITY_DEFAULT,
    PNG_COMPRESSION_DEFAULT
)
from core.converter import (
    ConversionConfig,
    ConversionResult,
    BatchConverter,
    scan_raw_files,
    scan_multiple_folders
)


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base_path, relative_path)
    if os.path.exists(p):
        return p
    fallback = os.path.join(base_path, os.path.basename(relative_path))
    if os.path.exists(fallback):
        return fallback
    return p


def format_bytes(num_bytes: int) -> str:
    """Format bytes into human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


class SupportedFormatsDialog(ctk.CTkToplevel):
    """Dialog showing all supported camera RAW formats grouped by manufacturer."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Ruvex - Supported Camera RAW Formats (25+ Extensions)")
        self.geometry("640x540")
        self.minsize(500, 400)
        self.transient(parent)
        self.grab_set()

        # Set dialog icon if available
        ico_path = get_resource_path("assets/app.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        head_frame = ctk.CTkFrame(self, fg_color="transparent")
        head_frame.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")

        ctk.CTkLabel(
            head_frame,
            text="All Supported Camera RAW Formats",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            head_frame,
            text="Decoded with LibRaw 0.22 engine with full sensor color accuracy.",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        ).pack(anchor="w", pady=(2, 0))

        # Scrollable brand list
        scroll = ctk.CTkScrollableFrame(self, corner_radius=8)
        scroll.grid(row=1, column=0, padx=20, pady=8, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for brand, exts in SUPPORTED_FORMATS_BY_BRAND.items():
            card = ctk.CTkFrame(scroll, corner_radius=6)
            card.pack(fill="x", padx=4, pady=4)
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                card,
                text=brand,
                font=ctk.CTkFont(size=13, weight="bold"),
                width=160,
                anchor="w"
            ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

            exts_label = ctk.CTkLabel(
                card,
                text=", ".join(exts),
                font=ctk.CTkFont(size=12),
                text_color="#64b5f6",
                anchor="w",
                justify="left"
            )
            exts_label.grid(row=0, column=1, padx=12, pady=8, sticky="w")

        # Bottom Close button
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=20, pady=(8, 16), sticky="ew")

        close_btn = ctk.CTkButton(btn_frame, text="Close", width=100, command=self.destroy)
        close_btn.pack(side="right")


class MultiFolderSelectDialog(ctk.CTkToplevel):
    """Dialog allowing user to add and manage multiple folders for batch conversion."""
    def __init__(self, parent, on_import_callback):
        super().__init__(parent)
        self.title("Ruvex - Select Multiple Folders")
        self.geometry("620x480")
        self.minsize(520, 380)
        self.transient(parent)
        self.grab_set()

        ico_path = get_resource_path("assets/app.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self.on_import_callback = on_import_callback
        self.selected_folders: List[str] = []
        self.folder_widgets: Dict[str, Any] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        ctk.CTkLabel(
            head,
            text="Add Multiple Folders",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            head,
            text="Browse and add multiple folders. All RAW files within them will be merged into the queue.",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        ).pack(anchor="w", pady=(2, 0))

        # Controls row
        btn_bar = ctk.CTkFrame(head, fg_color="transparent")
        btn_bar.pack(fill="x", pady=(10, 4))

        add_btn = ctk.CTkButton(
            btn_bar,
            text="+ Browse & Add Folder",
            fg_color="#1f538d",
            hover_color="#14375e",
            command=self._pick_folder
        )
        add_btn.pack(side="left")

        clear_all_btn = ctk.CTkButton(
            btn_bar,
            text="Clear List",
            fg_color="#5a2222",
            hover_color="#822828",
            width=80,
            command=self._clear_folders
        )
        clear_all_btn.pack(side="left", padx=8)

        self.recursive_var = tk.BooleanVar(value=True)
        self.rec_chk = ctk.CTkCheckBox(btn_bar, text="Scan Subfolders Recursively", variable=self.recursive_var)
        self.rec_chk.pack(side="right")

        # Scrollable folder list
        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.scroll.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        self.empty_lbl = ctk.CTkLabel(
            self.scroll,
            text="No folders added yet. Click '+ Browse & Add Folder' above.",
            font=ctk.CTkFont(size=13),
            text_color="gray60"
        )
        self.empty_lbl.pack(pady=40)

        # Bottom Action Bar
        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.grid(row=2, column=0, padx=16, pady=(8, 16), sticky="ew")

        self.summary_lbl = ctk.CTkLabel(foot, text="0 folders selected", font=ctk.CTkFont(size=12))
        self.summary_lbl.pack(side="left")

        cancel_btn = ctk.CTkButton(foot, text="Cancel", width=80, fg_color="#3a4750", hover_color="#303841", command=self.destroy)
        cancel_btn.pack(side="right", padx=(8, 0))

        import_btn = ctk.CTkButton(
            foot,
            text="Import RAW Files",
            fg_color="#2e7d32",
            hover_color="#1b5e20",
            font=ctk.CTkFont(weight="bold"),
            command=self._do_import
        )
        import_btn.pack(side="right")

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing RAW Images")
        if folder:
            abs_f = os.path.abspath(folder)
            if abs_f not in self.selected_folders:
                self.selected_folders.append(abs_f)
                self._create_folder_item(abs_f)
                self.empty_lbl.pack_forget()
                self._update_summary()

    def _create_folder_item(self, folder_path: str):
        row = ctk.CTkFrame(self.scroll, corner_radius=6)
        row.pack(fill="x", padx=4, pady=3)
        row.grid_columnconfigure(0, weight=1)

        name_lbl = ctk.CTkLabel(row, text=folder_path, anchor="w", font=ctk.CTkFont(size=12))
        name_lbl.grid(row=0, column=0, padx=10, pady=6, sticky="w")

        del_btn = ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=26,
            fg_color="#4f2020",
            hover_color="#8c2626",
            command=lambda p=folder_path: self._remove_folder(p)
        )
        del_btn.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        self.folder_widgets[folder_path] = row

    def _remove_folder(self, folder_path: str):
        if folder_path in self.selected_folders:
            self.selected_folders.remove(folder_path)
        if folder_path in self.folder_widgets:
            self.folder_widgets.pop(folder_path).destroy()
        if not self.selected_folders:
            self.empty_lbl.pack(pady=40)
        self._update_summary()

    def _clear_folders(self):
        self.selected_folders.clear()
        for widget in self.folder_widgets.values():
            widget.destroy()
        self.folder_widgets.clear()
        self.empty_lbl.pack(pady=40)
        self._update_summary()

    def _update_summary(self):
        cnt = len(self.selected_folders)
        self.summary_lbl.configure(text=f"{cnt} folder{'s' if cnt != 1 else ''} selected")

    def _do_import(self):
        if not self.selected_folders:
            messagebox.showwarning("No Folders", "Please add at least one folder.")
            return

        all_files = scan_multiple_folders(self.selected_folders, recursive=self.recursive_var.get())
        if all_files:
            self.on_import_callback(all_files)
            self.destroy()
        else:
            messagebox.showinfo("No RAW Files Found", "No supported camera RAW images were found in the selected folders.")


class RuvexApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Appearance configuration
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("Ruvex - RAW to Image Converter")
        self.geometry("1060x830")
        self.minsize(920, 710)

        # Set Window Icon
        ico_path = get_resource_path("assets/app.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        # File and state tracking
        self.file_queue: List[str] = []
        self.file_item_widgets: Dict[str, Dict[str, Any]] = {}
        self.converter_thread: Optional[threading.Thread] = None
        self.batch_converter: Optional[BatchConverter] = None
        self.is_converting = False
        self.start_conversion_time = 0.0

        self._build_ui()

    def _build_ui(self):
        # Main Grid Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # File list expands

        # ============================================================
        # 1. Header Frame with Ruvex Branding & Logo
        # ============================================================
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.grid(row=0, column=0, padx=16, pady=(16, 6), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_sub_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_sub_frame.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        # Load Ruvex Logo
        logo_path = get_resource_path("assets/Ruvex.png")
        if os.path.exists(logo_path):
            try:
                pil_logo = Image.open(logo_path)
                self.ruvex_logo = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(46, 46))
                logo_label = ctk.CTkLabel(title_sub_frame, image=self.ruvex_logo, text="")
                logo_label.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_text_box = ctk.CTkFrame(title_sub_frame, fg_color="transparent")
        title_text_box.pack(side="left")

        brand_row = ctk.CTkFrame(title_text_box, fg_color="transparent")
        brand_row.pack(anchor="w")

        title_label = ctk.CTkLabel(
            brand_row,
            text="Ruvex",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left")

        badge = ctk.CTkLabel(
            brand_row,
            text=" RAW Image Converter • PNG • WEBP • JPEG ",
            fg_color="#1f538d",
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        badge.pack(side="left", padx=12)

        header_right_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_right_frame.grid(row=0, column=1, padx=16, pady=8, sticky="e")

        formats_info_btn = ctk.CTkButton(
            header_right_frame,
            text="Supported Formats (25+) ℹ",
            fg_color="#2b3e50",
            hover_color="#374e63",
            width=170,
            command=self._show_supported_formats
        )
        formats_info_btn.pack(side="left", padx=(0, 10))

        theme_menu = ctk.CTkOptionMenu(
            header_right_frame,
            values=["Dark", "Light", "System"],
            command=ctk.set_appearance_mode,
            width=90
        )
        theme_menu.pack(side="left")
        theme_menu.set("Dark")

        # ============================================================
        # 2. Controls & Settings Cards (Two columns)
        # ============================================================
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        cards_frame.grid_columnconfigure(0, weight=1)
        cards_frame.grid_columnconfigure(1, weight=1)

        # Card Left: Source & Destination
        source_card = ctk.CTkFrame(cards_frame, corner_radius=8)
        source_card.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="nsew")

        src_title = ctk.CTkLabel(source_card, text="Files & Output Destination", font=ctk.CTkFont(size=14, weight="bold"))
        src_title.pack(anchor="w", padx=12, pady=(8, 4))

        btn_row = ctk.CTkFrame(source_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=3)

        add_files_btn = ctk.CTkButton(btn_row, text="+ Add Files", command=self._add_files, width=100)
        add_files_btn.pack(side="left", padx=(0, 4))

        add_folder_btn = ctk.CTkButton(btn_row, text="+ Add Folder", command=self._add_folder, width=105)
        add_folder_btn.pack(side="left", padx=3)

        # Dedicated Multiple Folders Button
        add_multi_folder_btn = ctk.CTkButton(
            btn_row,
            text="+ Add Multiple Folders",
            fg_color="#285943",
            hover_color="#1c4030",
            command=self._open_multi_folder_dialog,
            width=150
        )
        add_multi_folder_btn.pack(side="left", padx=3)

        clear_btn = ctk.CTkButton(
            btn_row,
            text="Clear All",
            fg_color="#852b2b",
            hover_color="#a83232",
            command=self._clear_queue,
            width=70
        )
        clear_btn.pack(side="right")

        # Destination controls
        dest_box = ctk.CTkFrame(source_card, fg_color="transparent")
        dest_box.pack(fill="x", padx=12, pady=(4, 8))

        dest_toggle_row = ctk.CTkFrame(dest_box, fg_color="transparent")
        dest_toggle_row.pack(fill="x", pady=(0, 2))

        self.custom_dest_var = tk.BooleanVar(value=False)
        self.dest_switch = ctk.CTkCheckBox(
            dest_toggle_row,
            text="Save to custom output directory",
            variable=self.custom_dest_var,
            command=self._toggle_dest_dir
        )
        self.dest_switch.pack(side="left")

        # Subfolder structure preservation checkbox (Optional, Checked by default!)
        self.keep_structure_var = tk.BooleanVar(value=True)
        self.keep_structure_chk = ctk.CTkCheckBox(
            dest_toggle_row,
            text="Preserve subfolder structure",
            variable=self.keep_structure_var
        )
        self.keep_structure_chk.pack(side="right")

        dest_input_row = ctk.CTkFrame(dest_box, fg_color="transparent")
        dest_input_row.pack(fill="x", pady=(2, 0))

        self.dest_entry = ctk.CTkEntry(dest_input_row, placeholder_text="Same folder as source RAW images", state="disabled")
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.dest_browse_btn = ctk.CTkButton(dest_input_row, text="Browse...", width=80, state="disabled", command=self._browse_dest)
        self.dest_browse_btn.pack(side="right")

        # Card Right: Conversion Engine Settings
        settings_card = ctk.CTkFrame(cards_frame, corner_radius=8)
        settings_card.grid(row=0, column=1, padx=(6, 0), pady=0, sticky="nsew")

        sett_title = ctk.CTkLabel(settings_card, text="Format, Resolution & Size Settings", font=ctk.CTkFont(size=14, weight="bold"))
        sett_title.pack(anchor="w", padx=12, pady=(8, 4))

        settings_grid = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_grid.pack(fill="x", padx=12, pady=2)
        settings_grid.grid_columnconfigure(0, weight=0)
        settings_grid.grid_columnconfigure(1, weight=1)

        # Output Format: PNG 1st (default), WEBP 2nd, JPEG 3rd
        ctk.CTkLabel(settings_grid, text="Format:", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, sticky="w", pady=2)
        self.format_var = ctk.StringVar(value="PNG (Lossless)")
        self.format_seg = ctk.CTkSegmentedButton(
            settings_grid,
            values=["PNG (Lossless)", "WEBP (~3MB)", "JPEG (~4MB)"],
            variable=self.format_var,
            command=self._on_format_changed
        )
        self.format_seg.grid(row=0, column=1, sticky="ew", pady=2)
        self.format_seg.set("PNG (Lossless)")

        # Resolution / Downscaling: Default Target < 10 MB (Auto-Fit)
        ctk.CTkLabel(settings_grid, text="Resolution:", font=ctk.CTkFont(size=12, weight="bold")).grid(row=1, column=0, sticky="w", pady=2)
        self.scale_menu = ctk.CTkOptionMenu(
            settings_grid,
            values=SCALE_OPTIONS,
            command=self._on_scale_changed
        )
        self.scale_menu.grid(row=1, column=1, sticky="ew", pady=2)
        self.scale_menu.set("Target < 10 MB (Auto-Fit)")

        # Format-specific option row
        self.sub_option_label = ctk.CTkLabel(settings_grid, text="Settings:", font=ctk.CTkFont(size=12, weight="bold"))
        self.sub_option_label.grid(row=2, column=0, sticky="w", pady=2)

        self.sub_option_container = ctk.CTkFrame(settings_grid, fg_color="transparent")
        self.sub_option_container.grid(row=2, column=1, sticky="ew", pady=2)
        self.sub_option_container.grid_columnconfigure(0, weight=1)

        # PNG options frame (Default: 8-bit Standard + Max Compression Level 9)
        self.png_options_frame = ctk.CTkFrame(self.sub_option_container, fg_color="transparent")
        self.png_options_frame.grid(row=0, column=0, sticky="ew")
        self.png_options_frame.grid_columnconfigure((0, 1), weight=1)

        self.bit_depth_var = ctk.StringVar(value="8-bit")
        self.bit_depth_seg = ctk.CTkSegmentedButton(
            self.png_options_frame,
            values=["8-bit (Standard)", "16-bit (HDR Pro)"],
            variable=self.bit_depth_var,
            command=self._on_bitdepth_changed
        )
        self.bit_depth_seg.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.bit_depth_seg.set("8-bit (Standard)")

        self.png_comp_menu = ctk.CTkOptionMenu(
            self.png_options_frame,
            values=["Max Compression (Level 9)", "Fast Compression (Level 3)"],
            width=140
        )
        self.png_comp_menu.grid(row=0, column=1, sticky="ew")
        self.png_comp_menu.set("Max Compression (Level 9)")

        # JPEG / WEBP Quality slider container
        self.jpeg_slider_frame = ctk.CTkFrame(self.sub_option_container, fg_color="transparent")
        self.jpeg_slider_frame.grid_columnconfigure(0, weight=1)

        self.jpeg_quality_var = tk.IntVar(value=95)
        self.jpeg_val_lbl = ctk.CTkLabel(self.jpeg_slider_frame, text="95%", font=ctk.CTkFont(size=12, weight="bold"), width=36)
        self.jpeg_val_lbl.pack(side="right")
        self.jpeg_slider = ctk.CTkSlider(
            self.jpeg_slider_frame,
            from_=60,
            to=100,
            number_of_steps=40,
            variable=self.jpeg_quality_var,
            command=lambda v: self.jpeg_val_lbl.configure(text=f"{int(v)}%")
        )
        self.jpeg_slider.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Helpful File Size Tip Banner
        self.tip_banner = ctk.CTkLabel(
            settings_card,
            text="💡 Default: 8-bit at 50% scale guarantees sharp PNGs under 10 MB (~6–8 MB)!",
            font=ctk.CTkFont(size=11),
            text_color="#81c784"
        )
        self.tip_banner.pack(anchor="w", padx=12, pady=(1, 2))

        # Toggles row (Preserve EXIF & Overwrite & Threads)
        toggles_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        toggles_row.pack(fill="x", padx=12, pady=(2, 6))

        self.metadata_var = tk.BooleanVar(value=True)
        self.meta_chk = ctk.CTkCheckBox(toggles_row, text="Preserve EXIF", variable=self.metadata_var)
        self.meta_chk.pack(side="left", padx=(0, 8))

        self.overwrite_var = tk.BooleanVar(value=False)
        self.over_chk = ctk.CTkCheckBox(toggles_row, text="Overwrite", variable=self.overwrite_var)
        self.over_chk.pack(side="left", padx=6)

        cpu_cores = min(16, os.cpu_count() or 4)
        ctk.CTkLabel(toggles_row, text="Threads:").pack(side="left", padx=(6, 4))
        self.threads_menu = ctk.CTkOptionMenu(toggles_row, values=[str(x) for x in range(1, cpu_cores + 1)], width=55)
        self.threads_menu.pack(side="left")
        self.threads_menu.set(str(min(4, cpu_cores)))

        # ============================================================
        # 3. Queue List Frame (Expandable)
        # ============================================================
        queue_outer = ctk.CTkFrame(self, corner_radius=10)
        queue_outer.grid(row=2, column=0, padx=16, pady=4, sticky="nsew")
        queue_outer.grid_rowconfigure(1, weight=1)
        queue_outer.grid_columnconfigure(0, weight=1)

        q_header = ctk.CTkFrame(queue_outer, fg_color="transparent")
        q_header.grid(row=0, column=0, padx=12, pady=(6, 4), sticky="ew")

        self.queue_count_label = ctk.CTkLabel(
            q_header,
            text="Queue: 0 files loaded",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.queue_count_label.pack(side="left")

        formats_summary_label = ctk.CTkLabel(
            q_header,
            text="Canon (CR2,CR3) • Nikon (NEF) • Sony (ARW) • Adobe (DNG) • Fuji (RAF) • Lumix (RW2) • Olympus • Pentax • Hasselblad",
            font=ctk.CTkFont(size=11),
            text_color="#90caf9"
        )
        formats_summary_label.pack(side="right")

        # Scrollable file list
        self.scroll_list = ctk.CTkScrollableFrame(queue_outer, corner_radius=6)
        self.scroll_list.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="nsew")
        self.scroll_list.grid_columnconfigure(0, weight=1)

        # Placeholder message when empty
        self.empty_label = ctk.CTkLabel(
            self.scroll_list,
            text="Drag files or click '+ Add Files' / '+ Add Multiple Folders' to begin",
            font=ctk.CTkFont(size=14),
            text_color="gray60"
        )
        self.empty_label.pack(pady=40)

        # ============================================================
        # 4. Progress & Action Bar
        # ============================================================
        action_frame = ctk.CTkFrame(self, corner_radius=10)
        action_frame.grid(row=3, column=0, padx=16, pady=(4, 14), sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)

        progress_info_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        progress_info_frame.grid(row=0, column=0, padx=16, pady=(8, 2), sticky="ew")
        progress_info_frame.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            progress_info_frame,
            text="Ready",
            font=ctk.CTkFont(size=13)
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        self.speed_label = ctk.CTkLabel(
            progress_info_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        self.speed_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(action_frame)
        self.progress_bar.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        self.progress_bar.set(0)

        action_btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
        action_btn_row.grid(row=2, column=0, padx=16, pady=(4, 10), sticky="ew")

        self.open_dest_btn = ctk.CTkButton(
            action_btn_row,
            text="Open Output Folder",
            fg_color="#3a4750",
            hover_color="#303841",
            state="disabled",
            command=self._open_output_folder
        )
        self.open_dest_btn.pack(side="left")

        self.convert_btn = ctk.CTkButton(
            action_btn_row,
            text="Convert to PNG",
            fg_color="#1f538d",
            hover_color="#14375e",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            width=180,
            command=self._on_convert_click
        )
        self.convert_btn.pack(side="right")

    # ============================================================
    # UI Event Handlers
    # ============================================================
    def _show_supported_formats(self):
        SupportedFormatsDialog(self)

    def _open_multi_folder_dialog(self):
        MultiFolderSelectDialog(self, on_import_callback=self._append_files)

    def _on_format_changed(self, choice: str):
        if "PNG" in choice:
            self.sub_option_label.configure(text="Settings:")
            self.jpeg_slider_frame.grid_forget()
            self.png_options_frame.grid(row=0, column=0, sticky="ew")
            self.convert_btn.configure(text="Convert to PNG")
            self._update_png_tip()
        elif "WEBP" in choice:
            self.sub_option_label.configure(text="Quality:")
            self.png_options_frame.grid_forget()
            self.jpeg_slider_frame.grid(row=0, column=0, sticky="ew")
            self.convert_btn.configure(text="Convert to WEBP")
            self.tip_banner.configure(
                text="💡 Tip: WebP produces crisp modern ~2–4 MB images with full camera EXIF.",
                text_color="#81c784"
            )
        elif "JPEG" in choice:
            self.sub_option_label.configure(text="Quality:")
            self.png_options_frame.grid_forget()
            self.jpeg_slider_frame.grid(row=0, column=0, sticky="ew")
            self.convert_btn.configure(text="Convert to JPEG")
            self.tip_banner.configure(
                text="💡 Tip: JPEG produces compact ~3–5 MB photos with camera EXIF.",
                text_color="#81c784"
            )

    def _on_scale_changed(self, choice: str):
        if "PNG" in self.format_var.get():
            self._update_png_tip()

    def _on_bitdepth_changed(self, choice: str):
        self._update_png_tip()

    def _update_png_tip(self):
        scale = self.scale_menu.get()
        is_16bit = "16-bit" in self.bit_depth_var.get()

        if is_16bit:
            self.tip_banner.configure(
                text="⚠️ Warning: 16-bit HDR uses 6 bytes/pixel -> file will be 120–135 MB! Switch to 8-bit for compact size.",
                text_color="#ff7043"
            )
        elif "Auto-Fit" in scale:
            self.tip_banner.configure(
                text="💡 Target < 10 MB (Auto-Fit): Dynamically ensures every photo stays strictly under 10 MB (~7–9 MB)!",
                text_color="#81c784"
            )
        elif "40%" in scale:
            self.tip_banner.configure(
                text="💡 40% Scale (2408x1606): Ultra-crisp high-res photo under 8 MB (~7–8 MB).",
                text_color="#81c784"
            )
        elif "35%" in scale:
            self.tip_banner.configure(
                text="💡 35% Scale (2107x1405): Safe size comfortably around 5–6 MB.",
                text_color="#81c784"
            )
        elif "2K" in scale:
            self.tip_banner.configure(
                text="💡 2K QHD (2560px max): Sharp 1440p monitor resolution (~7–9 MB).",
                text_color="#81c784"
            )
        elif "Full HD" in scale:
            self.tip_banner.configure(
                text="💡 Full HD (1920px max): Standard 1080p display resolution (~4–5 MB).",
                text_color="#81c784"
            )
        elif "50%" in scale:
            self.tip_banner.configure(
                text="💡 50% Scale: Produces ~11–13 MB PNGs on high-detail RAW photos.",
                text_color="#64b5f6"
            )
        else:
            self.tip_banner.configure(
                text="⚠️ Original 100% 8-bit PNG is ~35–52 MB. Use Target < 10 MB or 40% scale for small files.",
                text_color="#ffa726"
            )

    def _toggle_dest_dir(self):
        if self.custom_dest_var.get():
            self.dest_entry.configure(state="normal")
            self.dest_browse_btn.configure(state="normal")
        else:
            self.dest_entry.configure(state="disabled")
            self.dest_browse_btn.configure(state="disabled")

    def _browse_dest(self):
        folder = filedialog.askdirectory(title="Select Output Directory for Images")
        if folder:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, os.path.abspath(folder))

    def _add_files(self):
        filetypes = [
            ("All Supported RAW Images", "*.cr2 *.cr3 *.crw *.nef *.nrw *.arw *.srf *.sr2 *.dng *.raf *.rw2 *.raw *.orf *.ori *.pef *.ptx *.3fr *.fff *.iiq *.erf *.mef *.mos *.rwl *.srw *.x3f"),
            ("All files (*.*)", "*.*")
        ]
        selected = filedialog.askopenfilenames(title="Select Camera RAW Images", filetypes=filetypes)
        if selected:
            self._append_files(list(selected))

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing RAW Images")
        if folder:
            found = scan_raw_files(folder, recursive=True)
            if found:
                self._append_files(found)
            else:
                messagebox.showinfo("No RAW Files Found", f"No supported RAW images were found in:\n{folder}")

    def _append_files(self, paths: List[str]):
        new_count = 0
        for p in paths:
            abs_p = os.path.abspath(p)
            if abs_p not in self.file_queue:
                ext = Path(abs_p).suffix.lower()
                if ext in SUPPORTED_RAW_EXTENSIONS:
                    self.file_queue.append(abs_p)
                    self._create_queue_item_widget(abs_p)
                    new_count += 1

        if self.file_queue:
            self.empty_label.pack_forget()

        self._update_queue_label()

    def _create_queue_item_widget(self, file_path: str):
        row_frame = ctk.CTkFrame(self.scroll_list, corner_radius=6)
        row_frame.pack(fill="x", padx=4, pady=2)
        row_frame.grid_columnconfigure(0, weight=1)

        filename = Path(file_path).name
        size_str = format_bytes(os.path.getsize(file_path)) if os.path.exists(file_path) else "0 B"

        name_lbl = ctk.CTkLabel(
            row_frame,
            text=f"{filename}  ({size_str})",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        name_lbl.grid(row=0, column=0, padx=8, pady=4, sticky="w")

        right_controls = ctk.CTkFrame(row_frame, fg_color="transparent")
        right_controls.grid(row=0, column=1, padx=6, pady=4, sticky="e")

        status_badge = ctk.CTkLabel(
            right_controls,
            text="Queued",
            font=ctk.CTkFont(size=11),
            fg_color="#303841",
            corner_radius=4,
            width=80
        )
        status_badge.pack(side="left", padx=(0, 6))

        remove_btn = ctk.CTkButton(
            right_controls,
            text="✕",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#4f2020",
            hover_color="#8c2626",
            width=28,
            height=26,
            command=lambda p=file_path: self._remove_single_file(p)
        )
        remove_btn.pack(side="left")

        self.file_item_widgets[file_path] = {
            "frame": row_frame,
            "badge": status_badge,
            "name": name_lbl,
            "remove_btn": remove_btn
        }

    def _remove_single_file(self, file_path: str):
        if self.is_converting:
            messagebox.showwarning("Busy", "Cannot remove files while conversion is actively running.")
            return

        if file_path in self.file_queue:
            self.file_queue.remove(file_path)

        if file_path in self.file_item_widgets:
            widget_dict = self.file_item_widgets.pop(file_path)
            widget_dict["frame"].destroy()

        if not self.file_queue:
            self.empty_label.pack(pady=40)
            self.progress_bar.set(0)
            self.status_label.configure(text="Ready")
            self.speed_label.configure(text="")

        self._update_queue_label()

    def _clear_queue(self):
        if self.is_converting:
            messagebox.showwarning("Busy", "Cannot clear queue while conversion is running.")
            return

        self.file_queue.clear()
        for item in self.file_item_widgets.values():
            item["frame"].destroy()
        self.file_item_widgets.clear()

        self.empty_label.pack(pady=40)
        self._update_queue_label()
        self.progress_bar.set(0)
        self.status_label.configure(text="Ready")
        self.speed_label.configure(text="")

    def _update_queue_label(self):
        count = len(self.file_queue)
        self.queue_count_label.configure(text=f"Queue: {count} file{'s' if count != 1 else ''} loaded")

    def _open_output_folder(self):
        target = self.dest_entry.get().strip()
        if not target or not os.path.exists(target):
            if self.file_queue and os.path.exists(self.file_queue[0]):
                target = str(Path(self.file_queue[0]).parent)
            else:
                target = os.getcwd()

        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", target])
        else:
            subprocess.run(["xdg-open", target])

    # ============================================================
    # Conversion Management
    # ============================================================
    def _on_convert_click(self):
        if self.is_converting:
            if self.batch_converter:
                self.batch_converter.request_cancel()
            self.convert_btn.configure(text="Cancelling...", state="disabled")
            self.status_label.configure(text="Cancelling conversion...")
            return

        if not self.file_queue:
            messagebox.showwarning("Queue Empty", "Please add at least one RAW image file.")
            return

        # Prepare configuration
        raw_fmt = self.format_var.get()
        if "WEBP" in raw_fmt:
            target_format = "WEBP"
        elif "JPEG" in raw_fmt:
            target_format = "JPEG"
        else:
            target_format = "PNG"

        bit_depth = 16 if "16-bit" in self.bit_depth_var.get() else 8
        scale_mode = self.scale_menu.get()
        comp_level = 9 if "Level 9" in self.png_comp_menu.get() else 3
        custom_out = self.dest_entry.get().strip() if self.custom_dest_var.get() else None

        config = ConversionConfig(
            output_format=target_format,
            scale_mode=scale_mode,
            jpeg_quality=int(self.jpeg_quality_var.get()),
            compression_level=comp_level,
            bit_depth=bit_depth,
            white_balance="Camera",
            color_space="sRGB",
            demosaic_algorithm="AHD",
            preserve_metadata=self.metadata_var.get(),
            output_dir=custom_out if custom_out else None,
            overwrite=self.overwrite_var.get(),
            keep_subfolder_structure=self.keep_structure_var.get()
        )

        workers = int(self.threads_menu.get())

        for fpath, widget_dict in self.file_item_widgets.items():
            widget_dict["badge"].configure(text="Queued", fg_color="#303841")
            widget_dict["remove_btn"].configure(state="disabled")

        self.is_converting = True
        self.convert_btn.configure(text="Cancel", fg_color="#b23b3b", hover_color="#8b1e1e", state="normal")
        self.open_dest_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.start_conversion_time = time.time()

        self.batch_converter = BatchConverter(
            files=list(self.file_queue),
            config=config,
            max_workers=workers,
            progress_callback=self._on_worker_progress
        )

        self.converter_thread = threading.Thread(target=self._run_conversion_worker, daemon=True)
        self.converter_thread.start()

    def _run_conversion_worker(self):
        results = self.batch_converter.run()
        self.after(0, self._on_conversion_finished, results)

    def _on_worker_progress(self, completed: int, total: int, res: ConversionResult):
        self.after(0, self._update_ui_progress, completed, total, res)

    def _update_ui_progress(self, completed: int, total: int, res: ConversionResult):
        ratio = completed / total if total > 0 else 0
        self.progress_bar.set(ratio)

        elapsed = time.time() - self.start_conversion_time
        speed = completed / elapsed if elapsed > 0 else 0.0

        filename = Path(res.input_path).name
        self.status_label.configure(text=f"Processing [{completed}/{total}]: {filename}")
        self.speed_label.configure(text=f"{speed:.1f} files/sec | Elapsed: {elapsed:.1f}s")

        if res.input_path in self.file_item_widgets:
            badge = self.file_item_widgets[res.input_path]["badge"]
            if res.success:
                out_size_str = format_bytes(res.output_size_bytes)
                badge.configure(text=f"✓ {out_size_str}", fg_color="#2e7d32")
            else:
                badge.configure(text="✗ Failed", fg_color="#c62828")

    def _on_conversion_finished(self, results: List[ConversionResult]):
        self.is_converting = False
        raw_fmt = self.format_var.get()
        fmt_name = "WEBP" if "WEBP" in raw_fmt else ("JPEG" if "JPEG" in raw_fmt else "PNG")
        self.convert_btn.configure(text=f"Convert to {fmt_name}", fg_color="#1f538d", hover_color="#14375e", state="normal")
        self.open_dest_btn.configure(state="normal")

        for fpath, widget_dict in self.file_item_widgets.items():
            widget_dict["remove_btn"].configure(state="normal")

        total = len(results)
        succeeded = sum(1 for r in results if r.success)
        total_time = time.time() - self.start_conversion_time
        total_out_size = sum(r.output_size_bytes for r in results if r.success)

        if self.batch_converter and self.batch_converter.is_cancelled:
            self.status_label.configure(text=f"Conversion cancelled. {succeeded}/{total} completed.")
        else:
            self.status_label.configure(text=f"Finished! {succeeded}/{total} converted ({format_bytes(total_out_size)}) in {total_time:.1f}s.")
            messagebox.showinfo(
                "Conversion Complete",
                f"Successfully converted {succeeded} of {total} images.\n"
                f"Total Saved Size: {format_bytes(total_out_size)}\n"
                f"Total Duration: {total_time:.2f} seconds."
            )


def main():
    app = RuvexApp()
    app.mainloop()


if __name__ == "__main__":
    main()

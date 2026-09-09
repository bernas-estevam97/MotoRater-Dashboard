"""Safe file and directory selection utilities supporting both local GUI and headless/cloud environments."""

import os
import sys

_GUI_CHECK_CACHE = None


def is_gui_available() -> bool:
    """
    Check if a native GUI environment (e.g., Tkinter) can be invoked safely.
    Returns False in headless containers, Streamlit Cloud, or systems without a display server.
    """
    global _GUI_CHECK_CACHE
    if _GUI_CHECK_CACHE is not None:
        return _GUI_CHECK_CACHE

    # Streamlit Cloud indicator or explicit headless flag
    if os.environ.get("STREAMLIT_SERVER_HEADLESS", "").lower() in ("true", "1"):
        # On Windows local machines, HEADLESS might be passed via command line, but GUI still exists
        if sys.platform != "win32":
            _GUI_CHECK_CACHE = False
            return False

    # Non-Windows without DISPLAY or WAYLAND_DISPLAY
    if sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        _GUI_CHECK_CACHE = False
        return False

    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        _GUI_CHECK_CACHE = True
        return True
    except Exception:
        _GUI_CHECK_CACHE = False
        return False


def safe_select_folder(title: str = "Select Folder") -> str:
    """
    Opens a native folder picker dialog if GUI is supported.
    Returns empty string if canceled or if GUI is unavailable.
    """
    if not is_gui_available():
        return ""

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder_path = filedialog.askdirectory(master=root, title=title)
        root.destroy()
        return folder_path or ""
    except Exception:
        return ""


def safe_select_files(title: str = "Select Files", filetypes=None) -> list[str]:
    """
    Opens a native multiple-file picker dialog if GUI is supported.
    Returns empty list if canceled or if GUI is unavailable.
    """
    if not is_gui_available():
        return []

    if filetypes is None:
        filetypes = [("All Files", "*.*")]

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        file_paths = filedialog.askopenfilenames(master=root, title=title, filetypes=filetypes)
        root.destroy()
        return list(file_paths) if file_paths else []
    except Exception:
        return []

"""
Zalo Contact Renamer  — GUI
Run:  python main.py
"""

import datetime
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import os

import pyautogui
from config_manager import Config, load_config, save_config, TPL_INFO, TPL_NICK_LBL, TPL_NICK_ICON
from tracker import ContactTracker
from log_manager import LogManager
from automation import ZaloAutomation

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Palette ───────────────────────────────────────────────────────────────────
BG      = "#12121f"
PANEL   = "#1c1c30"
CARD    = "#22223a"
ACCENT  = "#6d28d9"
GREEN   = "#22c55e"
RED     = "#ef4444"
YELLOW  = "#f59e0b"
BLUE    = "#60a5fa"
FG      = "#e2e8f0"
FG2     = "#7c7c9a"
ENTRY   = "#0d0d1a"
BORDER  = "#2e2e50"
ARMED   = "#92400e"


# ── Widget helpers ────────────────────────────────────────────────────────────

def lbl(parent, text, fg=FG, size=10, bold=False, wrap=0, **kw):
    f = ("Segoe UI", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, bg=parent["bg"], fg=fg,
                    font=f, justify="left", wraplength=wrap, anchor="w", **kw)


def btn(parent, text, cmd, bg=ACCENT, fg="#fff", **kw):
    return tk.Button(parent, text=text, command=cmd,
                     bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                     relief="flat", bd=0, padx=13, pady=7,
                     font=("Segoe UI", 10, "bold"), cursor="hand2", **kw)


def ent(parent, width=18):
    e = tk.Entry(parent, bg=ENTRY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 10),
                 highlightthickness=1, highlightbackground=BORDER, width=width)
    return e


def sep(parent):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=6)


# ── Full-screen overlays ──────────────────────────────────────────────────────

class RegionPicker:
    """Dim full-screen overlay; user drags a rectangle."""
    def __init__(self, on_done):
        self.on_done = on_done
        self.sx = self.sy = 0
        self.rect_id = None
        r = tk.Toplevel()
        r.attributes("-fullscreen", True)
        r.attributes("-alpha", 0.28)
        r.attributes("-topmost", True)
        r.configure(bg="gray6")
        self.root = r
        c = tk.Canvas(r, cursor="crosshair", bg="gray6", highlightthickness=0)
        c.pack(fill="both", expand=True)
        self.canvas = c
        tk.Label(r,
                 text="Drag to select the contact list panel  |  Esc = cancel",
                 bg="gray6", fg="white", font=("Segoe UI", 13, "bold")
                 ).place(relx=0.5, rely=0.02, anchor="n")
        c.bind("<ButtonPress-1>",   self._press)
        c.bind("<B1-Motion>",       self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        r.bind("<Escape>", lambda _: r.destroy())

    def _press(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _drag(self, e):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        x0, y0 = min(self.sx, e.x_root), min(self.sy, e.y_root)
        x1, y1 = max(self.sx, e.x_root), max(self.sy, e.y_root)
        self.rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="#6d28d9", width=3,
            fill="#6d28d9", stipple="gray25")

    def _release(self, e):
        x = min(self.sx, e.x_root)
        y = min(self.sy, e.y_root)
        w = abs(e.x_root - self.sx)
        h = abs(e.y_root - self.sy)
        self.root.destroy()
        if w > 20 and h > 20:
            self.on_done(x, y, w, h)


class PointPicker:
    """Dim full-screen overlay; user clicks one point."""
    def __init__(self, instruction, on_done):
        self.on_done = on_done
        r = tk.Toplevel()
        r.attributes("-fullscreen", True)
        r.attributes("-alpha", 0.22)
        r.attributes("-topmost", True)
        r.configure(bg="gray6")
        self.root = r
        tk.Label(r, text=f"{instruction}\n\nPress  Esc  to cancel",
                 bg="gray6", fg="white",
                 font=("Segoe UI", 13, "bold"), justify="center"
                 ).place(relx=0.5, rely=0.04, anchor="n")
        c = tk.Canvas(r, bg="gray6", highlightthickness=0, cursor="crosshair")
        c.pack(fill="both", expand=True)
        c.bind("<Button-1>", self._pick)
        c.bind("<Motion>",   self._move)
        self.canvas = c
        self.h_line = c.create_line(0, 0, 0, 0, fill="#ef4444", width=1)
        self.v_line = c.create_line(0, 0, 0, 0, fill="#ef4444", width=1)
        r.bind("<Escape>", lambda _: r.destroy())

    def _move(self, e):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.canvas.coords(self.h_line, 0, e.y_root, sw, e.y_root)
        self.canvas.coords(self.v_line, e.x_root, 0, e.x_root, sh)

    def _pick(self, e):
        x, y = e.x_root, e.y_root
        self.root.destroy()
        self.on_done(x, y)


# ── Zalo-relative coordinate helpers ─────────────────────────────────────────

def abs_to_zalo_rel(abs_x: int, abs_y: int):
    hwnd = ZaloAutomation.find_zalo_hwnd()
    if hwnd and HAS_WIN32:
        rect = win32gui.GetWindowRect(hwnd)
        return [abs_x - rect[0], abs_y - rect[1]]
    return [abs_x, abs_y]


def abs_region_to_zalo_rel(ax: int, ay: int, aw: int, ah: int):
    hwnd = ZaloAutomation.find_zalo_hwnd()
    if hwnd and HAS_WIN32:
        rect = win32gui.GetWindowRect(hwnd)
        return [ax - rect[0], ay - rect[1], aw, ah]
    return [ax, ay, aw, ah]


# ── F9 template-capture helpers ───────────────────────────────────────────────

def arm_f9_capture(tpl_path: str, on_done_safe):
    """
    Register a one-shot F9 global hotkey.
    Captures 64x64 px around cursor and saves to tpl_path.
    Calls on_done_safe(ok: bool, info: str) from a background thread.
    """
    try:
        import keyboard
    except ImportError:
        on_done_safe(False, "keyboard library not installed -- run: pip install keyboard")
        return

    try:
        keyboard.remove_hotkey("f9")
    except Exception:
        pass

    def _capture():
        try:
            keyboard.remove_hotkey("f9")
        except Exception:
            pass
        try:
            x, y = pyautogui.position()
            s = 64
            img = pyautogui.screenshot(region=(x - s // 2, y - s // 2, s, s))
            folder = os.path.dirname(os.path.abspath(tpl_path))
            os.makedirs(folder, exist_ok=True)
            img.save(tpl_path)
            on_done_safe(True, tpl_path)
        except Exception as exc:
            on_done_safe(False, str(exc))

    keyboard.add_hotkey("f9", _capture, suppress=True)


def disarm_f9():
    try:
        import keyboard
        keyboard.remove_hotkey("f9")
    except Exception:
        pass


# ── Application ───────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Zalo Contact Renamer")
        self.root.geometry("1060x780")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        self.cfg        = load_config()
        self.tracker    = ContactTracker()
        self.log_mgr    = LogManager(self.cfg.log_file)
        self.automation = None
        self.thread     = None

        self._tpl_photos = {}   # keep PhotoImage refs alive to prevent GC

        self._build()
        self._cfg_to_ui()
        self._refresh_calib()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        tbar = tk.Frame(self.root, bg=ACCENT, height=50)
        tbar.pack(fill="x")
        tbar.pack_propagate(False)
        lbl(tbar, "  Zalo Contact Renamer", fg="#fff", size=14, bold=True).pack(
            side="left", pady=10)
        lbl(tbar, "  -- runs in background between renames", fg="#c4b5fd", size=9).pack(
            side="left", pady=10)

        s = ttk.Style()
        s.theme_use("default")
        s.configure("T.TNotebook", background=BG, borderwidth=0)
        s.configure("T.TNotebook.Tab", background=PANEL, foreground=FG2,
                    font=("Segoe UI", 10), padding=[14, 6])
        s.map("T.TNotebook.Tab",
              background=[("selected", CARD)],
              foreground=[("selected", FG)])

        self.nb = ttk.Notebook(self.root, style="T.TNotebook")
        self.nb.pack(fill="both", expand=True)

        self._tab_main()
        self._tab_calibrate()
        self._tab_config()
        self._tab_logs()

        sb = tk.Frame(self.root, bg="#090912", height=26)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.var_status = tk.StringVar(value="Ready -- complete Calibration first")
        self.var_count  = tk.StringVar(value="Renamed: 0")
        tk.Label(sb, textvariable=self.var_status, bg="#090912", fg=FG2,
                 font=("Segoe UI", 9), anchor="w").pack(side="left",  padx=10, fill="y")
        tk.Label(sb, textvariable=self.var_count,  bg="#090912", fg=GREEN,
                 font=("Segoe UI", 9), anchor="e").pack(side="right", padx=10, fill="y")

    # ── Tab: Main ─────────────────────────────────────────────────────────────

    def _tab_main(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="  >  Main  ")

        row0 = tk.Frame(f, bg=BG)
        row0.pack(fill="x", padx=20, pady=(16, 8))

        self.btn_start  = btn(row0, "Start",  self._start,  GREEN)
        self.btn_pause  = btn(row0, "Pause",  self._pause,  YELLOW, state="disabled")
        self.btn_resume = btn(row0, "Resume", self._resume, ACCENT, state="disabled")
        self.btn_stop   = btn(row0, "Stop",   self._stop,   RED,    state="disabled")
        self.btn_test   = btn(row0, "Test 1 (dry)", self._test_one, CARD)

        for b in (self.btn_start, self.btn_pause, self.btn_resume,
                  self.btn_stop, self.btn_test):
            b.pack(side="left", padx=(0, 8))

        btn(row0, "Clear session", self._clear_session, "#2d2d50").pack(side="right")

        diag_row = tk.Frame(f, bg=BG)
        diag_row.pack(fill="x", padx=20, pady=(0, 4))
        btn(diag_row, "Diagnose: click contact #1",
            self._debug_click, "#1e3a5f").pack(side="left", padx=(0, 8))
        lbl(diag_row,
            "Focuses Zalo and clicks row 1 -- verifies focus & click position "
            "before running the full workflow.",
            fg=FG2, size=9).pack(side="left")

        pc = tk.Frame(f, bg=PANEL, pady=10, padx=14)
        pc.pack(fill="x", padx=20, pady=4)
        top = tk.Frame(pc, bg=PANEL)
        top.pack(fill="x")
        lbl(top, "Progress", fg=FG2, size=9).pack(side="left")
        self.var_prog_count = tk.StringVar(value="0 renamed")
        tk.Label(top, textvariable=self.var_prog_count, bg=PANEL, fg=GREEN,
                 font=("Segoe UI", 9)).pack(side="right")
        self.pbar = ttk.Progressbar(pc, mode="indeterminate")
        self.pbar.pack(fill="x", pady=(4, 4))
        self.var_prog_detail = tk.StringVar(value="Waiting to start...")
        tk.Label(pc, textvariable=self.var_prog_detail, bg=PANEL, fg=FG2,
                 font=("Segoe UI", 9)).pack(anchor="w")

        lc = tk.Frame(f, bg=PANEL)
        lc.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        hdr = tk.Frame(lc, bg=PANEL)
        hdr.pack(fill="x", padx=8, pady=(8, 0))
        lbl(hdr, "Activity Log", fg=FG2, size=9, bold=True).pack(side="left")
        btn(hdr, "Clear", self._clear_log_display, PANEL, FG2).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            lc, bg=ENTRY, fg=FG, insertbackground=FG,
            font=("Consolas", 9), relief="flat", state="disabled",
            wrap="word", height=22)
        self.log_box.pack(fill="both", expand=True, padx=8, pady=8)
        for tag, color in [("ok", GREEN), ("err", RED), ("warn", YELLOW),
                           ("info", BLUE), ("head", "#c084fc")]:
            self.log_box.tag_config(tag, foreground=color)

    # ── Tab: Calibrate ────────────────────────────────────────────────────────

    def _tab_calibrate(self):
        outer = tk.Frame(self.nb, bg=BG)
        self.nb.add(outer, text="  Calibrate  ")

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)

        f = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0, 0), window=f, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        f.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        lbl(f, "Calibration  --  5 steps", fg=FG, size=14, bold=True).pack(
            anchor="w", padx=24, pady=(18, 2))
        lbl(f,
            "Steps 1-3 use click overlays.  Steps 4-5 use the F9 key -- "
            "Zalo keeps focus so the template screenshot is accurate.",
            fg=FG2, size=10, wrap=840).pack(anchor="w", padx=24, pady=(0, 12))

        # ── Step 1 ────────────────────────────────────────────────────────
        c1 = self._card(f, "1", "Detect Zalo Window",
            "Identifies the Zalo PC window so all positions are stored\n"
            "relative to its top-left corner -- window movement won't break anything.")
        row1 = tk.Frame(c1, bg=CARD)
        row1.pack(fill="x", pady=(6, 0))
        btn(row1, "Detect Zalo Now", self._detect_zalo, ACCENT).pack(side="left", padx=(0, 10))
        self.lbl_zalo_info = lbl(row1, "Not detected", fg=YELLOW, size=9)
        self.lbl_zalo_info.pack(side="left")

        # ── Step 2 ────────────────────────────────────────────────────────
        c2 = self._card(f, "2", "Select Contact List Region",
            "Drag a rectangle over the full contact/chat list panel on the\n"
            "LEFT side of Zalo.  Include all rows; exclude the search bar.")
        self._instructions(c2, [
            "1. Make sure your Zalo contacts are visible (apply any filter first).",
            "2. Click  [Pick Region]  -- screen dims and shows a crosshair.",
            "3. Click at the TOP-LEFT corner of the contact list.",
            "4. Drag to the BOTTOM-RIGHT corner and release.",
        ])
        row2 = tk.Frame(c2, bg=CARD)
        row2.pack(fill="x", pady=(6, 0))
        btn(row2, "Pick Region", self._pick_region, ACCENT).pack(side="left", padx=(0, 10))
        self.lbl_region = lbl(row2, "Not set", fg=YELLOW, size=9)
        self.lbl_region.pack(side="left")
        btn(row2, "Test screenshot", self._test_screenshot, PANEL, FG2).pack(
            side="left", padx=(12, 0))

        # ── Step 3 ────────────────────────────────────────────────────────
        c3 = self._card(f, "3", "Measure Contact Row Height  (2 clicks)",
            "Click the centre of two adjacent contacts.\n"
            "The vertical distance lets the app calculate how many rows are visible.")
        self._instructions(c3, [
            "1. Scroll the contact list so at least 2 contacts are visible.",
            "2. Click  [Pick Contact 1]  -> click the exact centre of the FIRST row.",
            "3. Click  [Pick Contact 2]  -> click the exact centre of the SECOND row.",
        ])
        row3 = tk.Frame(c3, bg=CARD)
        row3.pack(fill="x", pady=(6, 0))
        btn(row3, "Pick Contact 1", self._pick_c1, ACCENT).pack(side="left", padx=(0, 8))
        btn(row3, "Pick Contact 2", self._pick_c2, ACCENT).pack(side="left", padx=(0, 10))
        self.lbl_height = lbl(row3, "Height: not set", fg=YELLOW, size=9)
        self.lbl_height.pack(side="left")

        # ── Step 4: Nickname Label Position ───────────────────────────────────
        c4 = self._card(f, "4", "Pick Nickname Label Position  (required)",
            "Click the centre of the 'Ten goi nho' label in Zalo's profile panel.\n"
            "The rename scan starts here and moves right to find the pencil icon.")
        self._instructions(c4, [
            "1. In Zalo, click any contact so the chat panel opens.",
            "2. Click the info icon to open the profile panel on the right.",
            "3. Scroll down in the panel until you see 'Ten goi nho'.",
            "4. Click  [Pick Label Position]  -- screen dims.",
            "5. Click the centre of the 'Ten goi nho' label text in Zalo.",
            "TIP: click on the label TEXT itself, not the pencil icon.",
        ])
        row4nick = tk.Frame(c4, bg=CARD)
        row4nick.pack(fill="x", pady=(6, 0))
        btn(row4nick, "Pick Label Position", self._pick_nickname_label, ACCENT).pack(
            side="left", padx=(0, 10))
        self.lbl_nickname_label_pos = lbl(row4nick, "Not set", fg=YELLOW, size=9)
        self.lbl_nickname_label_pos.pack(side="left")

        # ── Step 5: Info button template (optional) ────────────────────────
        c4 = self._card(f, "5", "Capture Info / Profile Button Template  (F9, optional)",
            "Screenshot of the info icon in the Zalo chat header.\n"
            "Used as fallback to open the profile panel if it closes during the run.")
        self._instructions(c4, [
            "1. In Zalo, click any contact so the chat panel opens.",
            "2. Locate the info icon in the top-right of the chat header.",
            "3. Click  [Arm F9]  below  (button turns orange = armed).",
            "4. Move your mouse over the icon in Zalo  (do NOT click it).",
            "5. Press  F9  -- the template is captured around your cursor.",
            "   TIP: cursor must be centred on the icon when you press F9.",
        ])
        row4 = tk.Frame(c4, bg=CARD)
        row4.pack(fill="x", pady=(6, 2))
        self.btn_arm_info = btn(row4, "Arm F9  (Info button)",
                                lambda: self._arm_capture(TPL_INFO, "info"), ACCENT)
        self.btn_arm_info.pack(side="left", padx=(0, 10))
        self.lbl_tpl_info = lbl(row4, "Not captured", fg=YELLOW, size=9)
        self.lbl_tpl_info.pack(side="left")
        row4b = tk.Frame(c4, bg=CARD)
        row4b.pack(fill="x")
        self.lbl_thumb_info = tk.Label(row4b, bg=CARD)
        self.lbl_thumb_info.pack(side="left", pady=(2, 4))

        # ── Step 6a: Nickname label template (optional) ────────────────────
        c5a = self._card(f, "6a", "Capture Nickname Label Template  (F9, optional)",
            "Screenshot of the 'Ten goi nho' label text in the profile panel.\n"
            "Used to locate the label before revealing the pencil icon.")
        self._instructions(c5a, [
            "1. Click the info icon in Zalo so the profile panel opens on the right.",
            "2. Find the label  'Ten goi nho'  (Nickname).",
            "3. Click  [Arm F9]  below.",
            "4. Hover your mouse over the LABEL TEXT in Zalo.",
            "5. Press  F9  to capture.",
        ])
        row5a = tk.Frame(c5a, bg=CARD)
        row5a.pack(fill="x", pady=(6, 2))
        self.btn_arm_lbl = btn(row5a, "Arm F9  (Nickname label)",
                               lambda: self._arm_capture(TPL_NICK_LBL, "nick_lbl"), ACCENT)
        self.btn_arm_lbl.pack(side="left", padx=(0, 10))
        self.lbl_tpl_nick_lbl = lbl(row5a, "Not captured", fg=YELLOW, size=9)
        self.lbl_tpl_nick_lbl.pack(side="left")
        row5ab = tk.Frame(c5a, bg=CARD)
        row5ab.pack(fill="x")
        self.lbl_thumb_nick_lbl = tk.Label(row5ab, bg=CARD)
        self.lbl_thumb_nick_lbl.pack(side="left", pady=(2, 4))

        # ── Step 6b: Nickname pencil icon template (optional) ──────────────
        c5b = self._card(f, "6b", "Capture Nickname Pencil Icon Template  (F9, optional)",
            "Screenshot of the edit icon that appears when hovering\n"
            "over the 'Ten goi nho' label.  Appears only on hover.")
        self._instructions(c5b, [
            "1. Profile panel must already be open (from Step 5a).",
            "2. Move your mouse over the  'Ten goi nho'  label -- the pencil appears.",
            "3. Keep hovering.  Click  [Arm F9]  below (the pencil may vanish briefly).",
            "4. Hover back over the pencil icon so it reappears.",
            "5. Press  F9  to capture.",
            "TIP: work quickly -- the pencil disappears when you stop hovering.",
        ])
        row5b = tk.Frame(c5b, bg=CARD)
        row5b.pack(fill="x", pady=(6, 2))
        self.btn_arm_icon = btn(row5b, "Arm F9  (Pencil icon)",
                                lambda: self._arm_capture(TPL_NICK_ICON, "nick_icon"), ACCENT)
        self.btn_arm_icon.pack(side="left", padx=(0, 10))
        self.lbl_tpl_nick_icon = lbl(row5b, "Not captured", fg=YELLOW, size=9)
        self.lbl_tpl_nick_icon.pack(side="left")
        row5bb = tk.Frame(c5b, bg=CARD)
        row5bb.pack(fill="x")
        self.lbl_thumb_nick_icon = tk.Label(row5bb, bg=CARD)
        self.lbl_thumb_nick_icon.pack(side="left", pady=(2, 4))

        # ── Summary + Test ────────────────────────────────────────────────
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(14, 0))

        sm = tk.Frame(f, bg=PANEL, pady=10, padx=14)
        sm.pack(fill="x", padx=24, pady=(8, 0))
        lbl(sm, "Calibration summary", fg=FG2, size=9, bold=True).pack(anchor="w")
        self.lbl_sum_region  = lbl(sm, "Region:          -", fg=FG2, size=9)
        self.lbl_sum_height  = lbl(sm, "Row height:      -", fg=FG2, size=9)
        self.lbl_sum_info    = lbl(sm, "Info template:   -", fg=FG2, size=9)
        self.lbl_sum_nick_l  = lbl(sm, "Nick label tpl:  -", fg=FG2, size=9)
        self.lbl_sum_nick_i  = lbl(sm, "Nick icon tpl:   -", fg=FG2, size=9)
        for l in (self.lbl_sum_region, self.lbl_sum_height,
                  self.lbl_sum_info, self.lbl_sum_nick_l, self.lbl_sum_nick_i):
            l.pack(anchor="w", pady=1)

        tr = tk.Frame(f, bg=BG)
        tr.pack(fill="x", padx=24, pady=(12, 4))
        btn(tr, "Test Full Workflow (1 contact, dry run)",
            self._test_one, GREEN).pack(side="left", padx=(0, 12))
        lbl(tr, "Verify all calibration steps work before the real run.",
            fg=FG2, size=9).pack(side="left")

        tr2 = tk.Frame(f, bg=BG)
        tr2.pack(fill="x", padx=24, pady=(0, 8))
        btn(tr2, "Test Filter Monitor",
            self._test_filter_monitor, "#1e3a5f", FG2).pack(side="left", padx=(0, 12))
        lbl(tr2,
            "Captures the search-bar fingerprint, saves it as PNG so you can "
            "see the exact area being watched, then immediately verifies the check passes.",
            fg=FG2, size=9, wrap=700).pack(side="left")

        tr3 = tk.Frame(f, bg=BG)
        tr3.pack(fill="x", padx=24, pady=(0, 24))
        btn(tr3, "Measure Scroll Speed",
            self._measure_scroll_speed, "#1e3a5f", FG2).pack(side="left", padx=(0, 12))
        _spx = self.cfg.scroll_pixels_per_sec
        self.lbl_scroll_speed_result = lbl(
            tr3,
            f"Measured: {_spx:.0f} px/s" if _spx > 0 else "Not measured yet",
            fg=GREEN if _spx > 0 else FG2, size=9)
        self.lbl_scroll_speed_result.pack(side="left")

    # ── Card / instruction helpers ────────────────────────────────────────────

    def _card(self, parent, step_num, title, description) -> tk.Frame:
        outer = tk.Frame(parent, bg=CARD, pady=12, padx=14)
        outer.pack(fill="x", padx=24, pady=(0, 8))
        hrow = tk.Frame(outer, bg=CARD)
        hrow.pack(fill="x")
        tk.Label(hrow, text=f" {step_num} ", bg=ACCENT, fg="#fff",
                 font=("Segoe UI", 10, "bold"), padx=5, pady=2).pack(side="left")
        lbl(hrow, f"  {title}", fg=FG, size=11, bold=True).pack(side="left")
        lbl(outer, description, fg=FG2, size=9, wrap=840).pack(anchor="w", pady=(6, 0))
        return outer

    def _instructions(self, parent, lines):
        for line in lines:
            is_tip = line.strip().startswith("TIP")
            color  = GREEN if is_tip else (FG if not line.startswith("   ") else FG2)
            lbl(parent, f"  {line}", fg=color, size=9).pack(anchor="w")

    # ── Template capture ──────────────────────────────────────────────────────

    def _arm_capture(self, tpl_path: str, key: str):
        lbl_map   = {"info":      self.lbl_tpl_info,
                     "nick_lbl":  self.lbl_tpl_nick_lbl,
                     "nick_icon": self.lbl_tpl_nick_icon}
        thumb_map = {"info":      self.lbl_thumb_info,
                     "nick_lbl":  self.lbl_thumb_nick_lbl,
                     "nick_icon": self.lbl_thumb_nick_icon}
        btn_map   = {"info":      self.btn_arm_info,
                     "nick_lbl":  self.btn_arm_lbl,
                     "nick_icon": self.btn_arm_icon}

        status_lbl = lbl_map[key]
        thumb_lbl  = thumb_map[key]
        arm_btn    = btn_map[key]

        disarm_f9()
        status_lbl.config(text="Armed -- hover element in Zalo, press  F9", fg=YELLOW)
        arm_btn.config(bg=ARMED)

        def _on_done(ok: bool, info: str):
            arm_btn.config(bg=ACCENT)
            if ok:
                status_lbl.config(text=f"Captured -> {os.path.basename(info)}", fg=GREEN)
                self._load_thumb(info, thumb_lbl)
                self._refresh_calib()
                self._append_log(f"Template saved: {info}", "ok")
            else:
                status_lbl.config(text=f"Error: {info}", fg=RED)
                self._append_log(f"Template capture error: {info}", "err")

        arm_f9_capture(tpl_path, lambda ok, info: self.root.after(0, _on_done, ok, info))

    def _load_thumb(self, path: str, label: tk.Label):
        if not HAS_PIL or not os.path.exists(path):
            return
        try:
            img   = Image.open(path).resize((80, 80), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self._tpl_photos[path] = photo
            label.config(image=photo, width=80, height=80,
                         bd=2, relief="solid", bg=BORDER)
        except Exception:
            pass

    # ── Calibration actions ───────────────────────────────────────────────────

    def _detect_zalo(self):
        hwnd = ZaloAutomation.find_zalo_hwnd()
        if not hwnd:
            self.lbl_zalo_info.config(text="Zalo not found -- open Zalo PC first", fg=RED)
            return
        if HAS_WIN32:
            rect  = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd)
            w = rect[2] - rect[0]; h = rect[3] - rect[1]
            self.lbl_zalo_info.config(
                text=f"'{title}'  at ({rect[0]}, {rect[1]})  size {w}x{h}px", fg=GREEN)
        self._append_log("Zalo window detected.", "ok")

    def _pick_region(self):
        self.root.iconify()
        time.sleep(0.5)

        def done(ax, ay, aw, ah):
            rel = abs_region_to_zalo_rel(ax, ay, aw, ah)
            self.cfg.contact_region = rel
            save_config(self.cfg)
            self.root.deiconify()
            self._refresh_calib()
            self._append_log(f"Contact region saved (Zalo-relative): {rel}", "ok")

        RegionPicker(done)

    def _pick_c1(self):
        self.root.iconify()
        time.sleep(0.5)

        def done(ax, ay):
            rel = abs_to_zalo_rel(ax, ay)
            self.cfg.contact1_rel = rel
            self._recompute_height()
            save_config(self.cfg)
            self.root.deiconify()
            self._refresh_calib()
            self._append_log(f"Contact-1 centre saved (rel): {rel}", "ok")

        PointPicker("Click the CENTRE of the  FIRST  contact row in Zalo", done)

    def _pick_c2(self):
        self.root.iconify()
        time.sleep(0.5)

        def done(ax, ay):
            rel = abs_to_zalo_rel(ax, ay)
            self.cfg.contact2_rel = rel
            self._recompute_height()
            save_config(self.cfg)
            self.root.deiconify()
            self._refresh_calib()
            self._append_log(f"Contact-2 centre saved (rel): {rel}", "ok")

        PointPicker("Click the CENTRE of the  SECOND (adjacent) contact row in Zalo", done)

    def _pick_nickname_label(self):
        self.root.iconify()
        time.sleep(0.5)

        def done(ax, ay):
            rel = abs_to_zalo_rel(ax, ay)
            self.cfg.nickname_label_rel = rel
            save_config(self.cfg)
            self.root.deiconify()
            self._refresh_calib()
            self._append_log(f"Nickname label position saved (rel): {rel}", "ok")

        PointPicker(
            "Click the centre of the 'Ten goi nho' label in Zalo's profile panel",
            done)

    def _recompute_height(self):
        c1, c2 = self.cfg.contact1_rel, self.cfg.contact2_rel
        if c1 and c2:
            h = abs(c2[1] - c1[1])
            if h > 5:
                self.cfg.contact_item_height = h
                rh  = self.cfg.contact_region[3] if self.cfg.contact_region else 0
                vis = int(rh / h) if h else 0
                self._append_log(f"Row height = {h}px  ->  ~{vis} rows visible", "info")

    def _test_screenshot(self):
        if not self.cfg.contact_region:
            messagebox.showwarning("No region", "Complete Step 2 first.")
            return
        hwnd = ZaloAutomation.find_zalo_hwnd()
        if not hwnd:
            messagebox.showwarning("Zalo not found", "Open Zalo PC first.")
            return
        try:
            from PIL import ImageGrab
            rect = win32gui.GetWindowRect(hwnd)
            rx, ry, rw, rh = self.cfg.contact_region
            img  = ImageGrab.grab(bbox=(rect[0]+rx, rect[1]+ry,
                                        rect[0]+rx+rw, rect[1]+ry+rh))
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "test_screenshot.png")
            img.save(path)
            self._append_log(f"Screenshot saved -> {path}", "ok")
            os.startfile(path)
        except Exception as e:
            self._append_log(f"Screenshot error: {e}", "err")

    def _refresh_calib(self):
        r = self.cfg.contact_region
        self.lbl_region.config(text=str(r) if r else "Not set",
                               fg=GREEN if r else YELLOW)
        self.lbl_sum_region.config(
            text=f"Region:          {r or '-'}", fg=GREEN if r else FG2)

        h  = self.cfg.contact_item_height
        rh = self.cfg.contact_region[3] if self.cfg.contact_region else 0
        if h:
            vis   = int(rh / h) if h else 0
            h_txt = f"{h}px  (~{vis} rows visible)"
            h_col = GREEN
        else:
            h_txt = "Not set"
            h_col = YELLOW
        self.lbl_height.config(text=h_txt, fg=h_col)
        self.lbl_sum_height.config(text=f"Row height:      {h_txt}",
                                   fg=GREEN if h else FG2)

        nl = self.cfg.nickname_label_rel
        nl_txt = str(nl) if nl else "Not set"
        self.lbl_nickname_label_pos.config(text=nl_txt, fg=GREEN if nl else YELLOW)

        for tpl_path, s_lbl, sm_lbl, th_lbl, label in [
            (TPL_INFO,      self.lbl_tpl_info,      self.lbl_sum_info,   self.lbl_thumb_info,     "Info template:  "),
            (TPL_NICK_LBL,  self.lbl_tpl_nick_lbl,  self.lbl_sum_nick_l, self.lbl_thumb_nick_lbl, "Nick label tpl: "),
            (TPL_NICK_ICON, self.lbl_tpl_nick_icon,  self.lbl_sum_nick_i, self.lbl_thumb_nick_icon, "Nick icon tpl:  "),
        ]:
            exists = os.path.exists(tpl_path)
            if exists:
                s_lbl.config(text=f"{os.path.basename(tpl_path)}", fg=GREEN)
                sm_lbl.config(text=f"{label} captured", fg=GREEN)
                if tpl_path not in self._tpl_photos:
                    self._load_thumb(tpl_path, th_lbl)
            else:
                s_lbl.config(text="Not captured", fg=YELLOW)
                sm_lbl.config(text=f"{label} -", fg=FG2)

    # ── Tab: Config ───────────────────────────────────────────────────────────

    def _tab_config(self):
        outer = tk.Frame(self.nb, bg=BG)
        self.nb.add(outer, text="  Config  ")

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        f  = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0, 0), window=f, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def section(title):
            s = tk.Frame(f, bg=PANEL)
            s.pack(fill="x", padx=24, pady=(14, 0))
            lbl(s, title, fg="#a78bfa", size=10, bold=True).pack(anchor="w", padx=12, pady=6)
            return s

        def row(parent, label_text):
            r = tk.Frame(parent, bg=PANEL)
            r.pack(fill="x", padx=12, pady=3)
            tk.Label(r, text=label_text, bg=PANEL, fg=FG,
                     font=("Segoe UI", 10), width=32, anchor="w").pack(side="left")
            return r

        def field(parent):
            e = ent(parent, 14)
            e.pack(side="left", padx=(0, 8))
            return e

        def chk(parent, var, note=""):
            c = tk.Checkbutton(parent, variable=var, bg=PANEL,
                               activebackground=PANEL, fg=FG,
                               selectcolor=ENTRY, relief="flat")
            c.pack(side="left")
            if note:
                lbl(parent, f"  {note}", fg=FG2, size=9).pack(side="left")

        s1 = section("Prefix & Numbering")
        self.e_prefix         = field(row(s1, "Prefix  (e.g. KH)"))
        self.e_startno        = field(row(s1, "Start Number"))
        self.e_contact_number = field(row(s1, "Contact Number  (per cycle)"))

        s2 = section("Timing  (seconds)")
        self.e_action   = field(row(s2, "Action delay  (after clicking contact)"))
        self.e_profile  = field(row(s2, "Profile delay  (after clicking info btn)"))
        self.e_scroll   = field(row(s2, "Scroll delay  (after scrolling, before next cycle)"))
        self.e_scroll_n = field(row(s2, "Scroll amount  (fallback when speed not measured)"))

        r_speed = row(s2, "Scroll Speed  (notches/sec, higher = faster)")
        self.e_scroll_speed = field(r_speed)
        lbl(r_speed, "  default 6 = easy to observe; increase for production",
            fg=FG2, size=9).pack(side="left")

        r_stime = row(s2, "Scroll Time  (seconds, 0 = scroll by notches)")
        self.e_scroll_time = field(r_stime)
        btn(r_stime, "Test Scroll", self._test_scroll, "#1e3a5f", FG2).pack(
            side="left", padx=(6, 0))

        r_smart = row(s2, "Smart Scroll")
        self.v_smart = tk.BooleanVar()
        chk(r_smart, self.v_smart,
            "auto-scroll exactly one page using measured speed (overrides Scroll Time)")
        self.v_smart.trace_add("write", lambda *_: self._update_smart_scroll_info())

        r_smart_info = tk.Frame(s2, bg=PANEL)
        r_smart_info.pack(fill="x", padx=12, pady=(0, 4))
        self.lbl_smart_info = lbl(r_smart_info, "", fg=FG2, size=9)
        self.lbl_smart_info.pack(anchor="w", padx=32)

        s3 = section("Reliability")
        self.e_retries    = field(row(s3, "Max retries per contact"))
        self.e_confidence = field(row(s3, "Template match confidence  (0.0-1.0)"))

        s4 = section("Mode")
        r_dry = row(s4, "Dry-Run Mode")
        self.v_dry = tk.BooleanVar()
        chk(r_dry, self.v_dry, "Preview only -- Zalo is NOT modified")

        r_bg = row(s4, "Background Mode")
        self.v_bg = tk.BooleanVar()
        chk(r_bg, self.v_bg, "Restore your window between renames (recommended)")

        r_stop = row(s4, "Stop on Error")
        self.v_stop = tk.BooleanVar()
        chk(r_stop, self.v_stop, "Halt the run if any rename fails")

        s5 = section("Log File")
        r_log = row(s5, "CSV log path")
        self.e_log = ent(r_log, 32)
        self.e_log.pack(side="left", padx=(0, 6))
        btn(r_log, "Browse", self._browse_log, PANEL, FG2).pack(side="left")

        brow = tk.Frame(f, bg=BG)
        brow.pack(fill="x", padx=24, pady=18)
        btn(brow, "Save Settings", self._save_cfg, ACCENT).pack(side="left")

    def _cfg_to_ui(self):
        def s(e, v):
            e.delete(0, "end")
            e.insert(0, str(v))
        s(self.e_prefix,         self.cfg.prefix)
        s(self.e_startno,        self.cfg.start_number)
        s(self.e_contact_number, self.cfg.contact_number)
        s(self.e_action,        self.cfg.action_delay)
        s(self.e_profile,       self.cfg.profile_delay)
        s(self.e_scroll,        self.cfg.scroll_delay)
        s(self.e_scroll_n,      self.cfg.scroll_amount)
        s(self.e_scroll_speed,  self.cfg.scroll_speed)
        s(self.e_scroll_time,   self.cfg.scroll_time)
        s(self.e_retries,      self.cfg.max_retries)
        s(self.e_confidence,   self.cfg.match_confidence)
        s(self.e_log,          self.cfg.log_file)
        self.v_dry.set(self.cfg.dry_run)
        self.v_bg.set(self.cfg.background_mode)
        self.v_stop.set(self.cfg.stop_on_error)
        self.v_smart.set(self.cfg.use_smart_scroll)
        self._update_smart_scroll_info()

    def _update_smart_scroll_info(self):
        if not hasattr(self, 'lbl_smart_info'):
            return
        if not self.v_smart.get():
            self.lbl_smart_info.config(text="")
            return
        r   = self.cfg.contact_region
        h   = self.cfg.contact_item_height
        spx = self.cfg.scroll_pixels_per_sec
        if not r or not h:
            self.lbl_smart_info.config(
                text="  Calibrate region (Step 2) and row height (Step 3) first",
                fg=YELLOW)
            return
        if spx <= 0:
            self.lbl_smart_info.config(
                text="  Measure scroll speed first (Calibrate tab -> Measure Scroll Speed)",
                fg=YELLOW)
            return
        rh   = r[3]
        rows = max(1, rh // h)
        t    = rh / spx
        self.lbl_smart_info.config(
            text=f"  {rh}px / {spx:.0f}px/s = {t:.2f}s per scroll, ~{rows} rows/page",
            fg=GREEN)

    def _save_cfg(self):
        try:
            self.cfg.prefix           = self.e_prefix.get().strip() or "KH"
            self.cfg.start_number     = int(self.e_startno.get())
            self.cfg.contact_number   = max(1, int(self.e_contact_number.get()))
            self.cfg.action_delay          = float(self.e_action.get())
            self.cfg.profile_delay         = float(self.e_profile.get())
            self.cfg.scroll_delay          = float(self.e_scroll.get())
            self.cfg.scroll_amount         = int(self.e_scroll_n.get())
            self.cfg.scroll_speed          = max(1.0, float(self.e_scroll_speed.get()))
            self.cfg.scroll_time           = max(0.0, float(self.e_scroll_time.get()))
            self.cfg.max_retries      = int(self.e_retries.get())
            self.cfg.match_confidence = float(self.e_confidence.get())
            self.cfg.log_file         = self.e_log.get().strip()
            self.cfg.dry_run          = self.v_dry.get()
            self.cfg.background_mode  = self.v_bg.get()
            self.cfg.stop_on_error    = self.v_stop.get()
            self.cfg.use_smart_scroll = self.v_smart.get()
        except ValueError as e:
            messagebox.showerror("Invalid value", str(e))
            return
        save_config(self.cfg)
        self.log_mgr.set_log_file(self.cfg.log_file)
        self._append_log("Settings saved.", "info")

    def _browse_log(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            self.e_log.delete(0, "end")
            self.e_log.insert(0, p)

    # ── Tab: Logs ─────────────────────────────────────────────────────────────

    def _tab_logs(self):
        f = tk.Frame(self.nb, bg=BG)
        self.nb.add(f, text="  Logs  ")

        tb = tk.Frame(f, bg=BG)
        tb.pack(fill="x", padx=16, pady=8)
        btn(tb, "Export CSV",   self._export_csv,   ACCENT).pack(side="left", padx=(0, 6))
        btn(tb, "Export Excel", self._export_excel, ACCENT).pack(side="left", padx=(0, 6))
        btn(tb, "Clear Logs",   self._clear_logs,   RED).pack(side="right")

        s = ttk.Style()
        s.configure("Log.Treeview", background=ENTRY, foreground=FG,
                    fieldbackground=ENTRY, font=("Segoe UI", 9), rowheight=24)
        s.configure("Log.Treeview.Heading", background=PANEL, foreground=FG2,
                    font=("Segoe UI", 9, "bold"))
        s.map("Log.Treeview", background=[("selected", ACCENT)])

        cols = ("No", "Original Name", "New Name", "Status", "Timestamp")
        tf = tk.Frame(f, bg=BG)
        tf.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                 style="Log.Treeview")
        for col, w in zip(cols, [40, 210, 240, 80, 155]):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="w")
        self.tree.tag_configure("ok",   foreground=GREEN)
        self.tree.tag_configure("fail", foreground=RED)
        self.tree.tag_configure("dry",  foreground=YELLOW)
        vsb2 = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb2.set)
        vsb2.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for r in self.log_mgr.get_records():
            tag = {"Success": "ok", "Failed": "fail", "Dry Run": "dry"}.get(r["Status"], "")
            self.tree.insert("", "end",
                             values=(r["No"], r["Original Name"],
                                     r["New Name"], r["Status"], r["Timestamp"]),
                             tags=(tag,))

    def _clear_logs(self):
        if messagebox.askyesno("Clear", "Remove all log entries?"):
            self.log_mgr.clear()
            self._refresh_tree()

    def _export_csv(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if p:
            self.log_mgr.export_csv(p)
            messagebox.showinfo("Exported", f"Saved:\n{p}")

    def _export_excel(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not p:
            return
        try:
            self.log_mgr.export_excel(p)
            messagebox.showinfo("Exported", f"Saved:\n{p}")
        except ImportError:
            messagebox.showerror("Error", "pandas/openpyxl not installed.")

    # ── Controls ──────────────────────────────────────────────────────────────

    def _make_auto(self) -> ZaloAutomation:
        return ZaloAutomation(
            config=self.cfg,
            tracker=self.tracker,
            log_manager=self.log_mgr,
            log_cb=self._log_safe,
            progress_cb=self._on_progress,
            status_cb=self._set_status,
        )

    def _check_calib(self) -> bool:
        missing = []
        if not self.cfg.contact_region:       missing.append("Contact region          (Step 2)")
        if not self.cfg.contact_item_height:  missing.append("Contact row height      (Step 3)")
        if not self.cfg.nickname_label_rel:   missing.append("Nickname label position (Step 4)")
        if missing:
            messagebox.showwarning(
                "Calibration incomplete",
                "Please complete these calibration steps first:\n\n- "
                + "\n- ".join(missing))
            self.nb.select(1)
            return False
        return True

    def _start(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo("Running", "Automation is already running.")
            return
        if not self._check_calib():
            return
        self._save_cfg()
        self.automation = self._make_auto()
        self.thread = threading.Thread(target=self.automation.run, daemon=True)
        self.thread.start()
        self.pbar.start(12)
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self.btn_resume.config(state="disabled")
        self.btn_test.config(state="disabled")

    def _pause(self):
        if self.automation:
            self.automation.pause()
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="normal")

    def _resume(self):
        if self.automation:
            self.automation.resume()
        self.btn_resume.config(state="disabled")
        self.btn_pause.config(state="normal")

    def _stop(self):
        if self.automation:
            self.automation.stop()
        disarm_f9()
        self._reset_btns()

    def _test_one(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo("Running", "Wait for current run to finish.")
            return
        if not self._check_calib():
            return
        self._save_cfg()
        self.automation = self._make_auto()
        self.thread = threading.Thread(target=self.automation.test_one, daemon=True)
        self.thread.start()

    def _debug_click(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo("Running", "Wait for current run to finish.")
            return
        if not self.cfg.contact_region or not self.cfg.contact_item_height:
            messagebox.showwarning(
                "Calibration needed",
                "Complete Steps 2 and 3 (contact region & row height) first.")
            self.nb.select(1)
            return
        auto = self._make_auto()
        self.thread = threading.Thread(target=auto.debug_click_contact, daemon=True)
        self.thread.start()

    def _measure_scroll_speed(self):
        """Scroll the list briefly, measure pixels moved per second, save to config."""
        self._save_cfg()
        if not self.cfg.contact_region:
            messagebox.showwarning("No region",
                "Complete calibration Step 2 (contact region) first.")
            return
        if not self.cfg.contact_item_height:
            messagebox.showwarning("No row height",
                "Complete calibration Step 3 (row height) first.")
            return
        self.root.iconify()
        time.sleep(0.4)
        auto = self._make_auto()
        def _run():
            try:
                if not auto.find_zalo_window():
                    self._log_safe("Measure scroll speed: Zalo window not found.")
                    return
                auto._focus_zalo()
                time.sleep(0.4)
                speed = auto.measure_scroll_speed()
                if speed:
                    self.cfg.scroll_pixels_per_sec = speed
                    save_config(self.cfg)
                    self._log_safe(f"Scroll speed saved: {speed:.1f} px/s")
                    self.root.after(0, self._on_scroll_speed_measured, speed)
                else:
                    self._log_safe("Scroll speed measurement failed — ensure the "
                                   "contact list has more content below the visible area.")
            finally:
                self.root.after(0, self.root.deiconify)
        threading.Thread(target=_run, daemon=True).start()

    def _on_scroll_speed_measured(self, speed: float):
        if hasattr(self, 'lbl_scroll_speed_result'):
            self.lbl_scroll_speed_result.config(
                text=f"Measured: {speed:.0f} px/s", fg=GREEN)
        self._update_smart_scroll_info()

    def _test_scroll(self):
        """Minimise GUI, scroll the Zalo contact list for scroll_time seconds, restore."""
        self._save_cfg()
        if not self.cfg.contact_region:
            messagebox.showwarning("No region",
                "Complete calibration Step 2 (contact region) first.")
            return
        smart_ok = self.cfg.use_smart_scroll and self.cfg.scroll_pixels_per_sec > 0
        if not smart_ok and self.cfg.scroll_time <= 0:
            messagebox.showinfo("Scroll not configured",
                "Either enable Smart Scroll (with measured speed) or set "
                "Scroll Time > 0 in the Config tab.")
            return
        self.root.iconify()
        time.sleep(0.4)
        auto = self._make_auto()
        def _run():
            try:
                if not auto.find_zalo_window():
                    self._log_safe("Test scroll: Zalo window not found.")
                    return
                auto._focus_zalo()
                time.sleep(0.4)
                auto._scroll_list()
                if self.cfg.use_smart_scroll and self.cfg.scroll_pixels_per_sec > 0:
                    rh = self.cfg.contact_region[3]
                    t  = rh / self.cfg.scroll_pixels_per_sec
                    self._log_safe(f"Test scroll done — smart scroll {t:.2f}s.")
                else:
                    self._log_safe(
                        f"Test scroll done — scrolled for {self.cfg.scroll_time:.2f}s.")
            finally:
                self.root.after(0, self.root.deiconify)
        threading.Thread(target=_run, daemon=True).start()

    def _test_filter_monitor(self):
        """Capture filter fingerprint, save as PNG, open it, and verify the check passes."""
        if not self.cfg.contact_region:
            messagebox.showwarning("No region",
                "Complete calibration Step 2 (contact region) first.")
            return
        self.root.iconify()
        time.sleep(0.4)
        auto = self._make_auto()
        def _run():
            try:
                if not auto.find_zalo_window():
                    self._log_safe("Filter monitor test: Zalo window not found.")
                    return
                auto._focus_zalo()
                time.sleep(0.3)
                ok = auto._capture_filter_fingerprint()
                if not ok or auto._filter_fingerprint is None:
                    self._log_safe("Filter monitor test: fingerprint capture failed.")
                    return
                # Save the captured strip as a PNG the user can inspect visually.
                try:
                    from PIL import Image
                    img  = Image.fromarray(auto._filter_fingerprint)
                    path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "test_filter_fingerprint.png")
                    img.save(path)
                    self._log_safe(f"Filter fingerprint saved -> {path}")
                    os.startfile(path)
                except Exception as exc:
                    self._log_safe(f"Filter fingerprint save error: {exc}")
                # Immediately re-check — should always pass right after capture.
                time.sleep(0.25)
                intact = auto._check_filter_intact()
                if intact:
                    self._log_safe(
                        "Filter check: OK — monitoring is active and working correctly.")
                else:
                    self._log_safe(
                        "Filter check: FAILED immediately after capture — "
                        "the screen changed between capture and re-check (unexpected).")
            finally:
                self.root.after(0, self.root.deiconify)
        threading.Thread(target=_run, daemon=True).start()

    def _clear_session(self):
        if messagebox.askyesno("Clear session",
                                "Reset processed-contact tracker?\n"
                                "All contacts will be eligible for renaming again."):
            self.tracker.clear()
            self._append_log("Session tracker cleared.", "warn")

    def _reset_btns(self):
        self.pbar.stop()
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled")
        self.btn_resume.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.btn_test.config(state="normal")

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, msg: str, tag: str = ""):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if not tag:
            ml = msg.lower()
            if any(k in ml for k in ("error", "failed", "failsafe")):
                tag = "err"
            elif any(k in ml for k in ("success", "renamed", "saved", "detected")):
                tag = "ok"
            elif any(k in ml for k in ("skip", "warn", "dry run", "not set")):
                tag = "warn"
            elif msg.startswith("===") or msg.startswith("---"):
                tag = "head"
            else:
                tag = "info"
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _log_safe(self, msg: str):
        self.root.after(0, self._append_log, msg)

    def _on_progress(self, count: int):
        def _update():
            self.var_count.set(f"Renamed: {count}")
            self.var_prog_count.set(f"{count} renamed")
            self.var_prog_detail.set(f"Total renamed this session: {count}")
            self._refresh_tree()
        self.root.after(0, _update)

    def _set_status(self, text: str):
        self.root.after(0, self.var_status.set, text)
        if "EMERGENCY STOP" in text:
            self.root.after(0, self._reset_btns)
            self.root.after(0, lambda: messagebox.showwarning(
                "EMERGENCY STOP",
                "The Zalo contact filter/search area changed unexpectedly.\n\n"
                "Automation has been halted immediately to prevent renaming\n"
                "the wrong contacts.\n\n"
                "Please verify your Zalo filter is still active before restarting."
            ))
        elif (text in ("Finished", "Stopped", "Not set up",
                       "Error -- Zalo not found", "Ready")
              or text.startswith("Completed —")
              or text.startswith("Stopped —")):
            self.root.after(0, self._reset_btns)
            if text.startswith("Completed —"):
                self.root.after(0, lambda t=text: messagebox.showinfo(
                    "Automation Complete", t.replace("Completed — ", "") + "\n\n"
                    "All target contacts have been processed."))

    def _clear_log_display(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    app  = App(root)
    root.protocol("WM_DELETE_WINDOW",
                  lambda: (app._stop() if app.automation else None,
                           disarm_f9(),
                           root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()

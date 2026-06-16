"""
Zalo Panel Diagnostic v3
========================
Fixes the y-coordinate issue from diag2: the previous scan was at y=64 absolute
(= y=28 relative to window top), which is the TITLE BAR — not the chat header.

This script:
  1. Focuses Zalo and clicks the first contact.
  2. Scans the chat header at CORRECT y values (zy+50 .. zy+130).
  3. Uses full-screenshot pixel-diff to detect any UI change.
  4. Tests keyboard shortcuts that might toggle the info panel.
  5. Tests right-click on a contact row in the list (might have "Set nickname").

Run:  python diag3.py
"""

import time, os, sys
import pyautogui

try:
    from PIL import ImageGrab
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("ERROR: Pillow not installed.  pip install Pillow")
    sys.exit(1)

try:
    import win32gui, win32con, win32process, win32api
    import win32com.client
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("ERROR: pywin32 not installed.")
    sys.exit(1)

OUT = r"C:\Users\Admin\Downloads\renameAPPS"
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03


# ── helpers ───────────────────────────────────────────────────────────────────

def grab():
    return np.array(ImageGrab.grab())


def save(arr, name):
    from PIL import Image
    path = os.path.join(OUT, name)
    Image.fromarray(arr).save(path)
    print(f"  Saved {name}")
    return path


def diff_px(a, b):
    """Number of pixels that changed by >15 in any channel."""
    d = np.abs(a.astype(np.int32) - b.astype(np.int32))
    return int((d.max(axis=2) > 15).sum())


def find_zalo():
    my_pid = os.getpid()
    found = []

    def _cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        title = win32gui.GetWindowText(h)
        if "Zalo" not in title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            if pid == my_pid:
                return
        except Exception:
            pass
        if win32gui.GetClassName(h) == "Chrome_WidgetWin_1":
            found.append(h)

    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None


def focus_zalo(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.35)
    if win32gui.GetForegroundWindow() == hwnd:
        return True

    # Method 1: WScript.Shell AppActivate
    try:
        title = win32gui.GetWindowText(hwnd)
        win32com.client.Dispatch("WScript.Shell").AppActivate(title)
        time.sleep(0.40)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception:
        pass

    # Method 2: Simulate Alt keypress — makes Windows allow SetForegroundWindow
    try:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)           # Alt down
        win32gui.SetForegroundWindow(hwnd)
        win32api.keybd_event(win32con.VK_MENU, 0,
                             win32con.KEYEVENTF_KEYUP, 0)           # Alt up
        time.sleep(0.30)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception:
        pass

    # Method 3: AttachThreadInput
    try:
        fg = win32gui.GetForegroundWindow()
        if fg and fg != hwnd:
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
            my_tid = win32api.GetCurrentThreadId()
            win32process.AttachThreadInput(fg_tid, my_tid, True)
            try:
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
            finally:
                win32process.AttachThreadInput(fg_tid, my_tid, False)
            time.sleep(0.30)
    except Exception:
        pass

    return win32gui.GetForegroundWindow() == hwnd


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Zalo Panel Diagnostic v3")
    print("=" * 60)

    hwnd = find_zalo()
    if not hwnd:
        print("ERROR: Zalo not found.")
        return

    rect = win32gui.GetWindowRect(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2 - zx, zy2 - zy
    print(f"Zalo hwnd={hwnd}  rect={rect}  size={zw}x{zh}")

    ok = focus_zalo(hwnd)
    print(f"Focus: {'OK - Zalo is foreground' if ok else 'FAILED'}")
    if not ok:
        print("Cannot proceed — Zalo is not focused.")
        return

    time.sleep(0.4)

    # ── Step 1: click first contact ──────────────────────────────────────────
    # contact_region (rel) = [66, 208, 335, 873], contact_item_height = 91
    cx = zx + 66 + int(335 * 0.38)          # ~193 from region left = zx+259
    cy = zy + 208 + 45                        # first contact centre
    print(f"\n[1] Clicking contact at ({cx}, {cy}) …")
    before_click = grab()
    save(before_click, "diag3_00_before.png")
    pyautogui.click(cx, cy)
    time.sleep(1.8)
    after_click = grab()
    save(after_click, "diag3_01_after_contact_click.png")
    changed = diff_px(before_click, after_click)
    print(f"    Pixels changed after contact click: {changed}")

    # ── Step 2: keyboard shortcut survey ────────────────────────────────────
    print("\n[2] Testing keyboard shortcuts for info panel …")
    shortcuts = [
        ("ctrl+i",       "Ctrl+I"),
        ("ctrl+shift+p", "Ctrl+Shift+P"),
        ("f4",           "F4"),
        ("f5",           "F5"),
        ("f6",           "F6"),
        ("alt+i",        "Alt+I"),
    ]
    for keys, label in shortcuts:
        b = grab()
        pyautogui.hotkey(*keys.split("+"))
        time.sleep(0.6)
        a = grab()
        ch = diff_px(b, a)
        if ch > 2000:
            save(b, f"diag3_kb_{label.replace('+','')}_before.png")
            save(a, f"diag3_kb_{label.replace('+','')}_after.png")
            print(f"  *** {label}: {ch} px changed — POSSIBLE HIT ***")
            # Close it again so we start fresh
            pyautogui.hotkey(*keys.split("+"))
            time.sleep(0.5)
        else:
            print(f"  {label}: {ch} px changed (no effect)")
        # Escape any stray dialog
        pyautogui.press("escape")
        time.sleep(0.25)

    # ── Step 3: header click scan at correct y range ─────────────────────────
    print("\n[3] Scanning header click positions (correct y range) …")
    # Previous scan was y=64 absolute = y=28 relative (title bar! wrong).
    # Chat header buttons should be at roughly zy+55 .. zy+120.
    # Right portion of window only (left side is contact list).
    best = None
    for y_rel in range(55, 135, 8):
        y_abs = zy + y_rel
        for x_abs in range(zx2 - 360, zx2 - 60, 20):
            b = grab()
            pyautogui.click(x_abs, y_abs)
            time.sleep(0.45)
            a = grab()
            ch = diff_px(b, a)
            if ch > 3000:
                label = f"diag3_hdr_{x_abs}_{y_abs}"
                save(b, f"{label}_before.png")
                save(a, f"{label}_after.png")
                print(f"  *** CHANGE at ({x_abs}, {y_abs}): {ch} px "
                      f"[y_rel={y_rel}] — PANEL TOGGLE CANDIDATE ***")
                best = (x_abs, y_abs, ch)
                # Toggle back
                pyautogui.click(x_abs, y_abs)
                time.sleep(0.5)
            else:
                print(f"  ({x_abs:4d}, {y_abs:3d}): {ch:5d} px")
            # Re-focus after each click (Electron may steal/drop focus)
            focus_zalo(hwnd)
            time.sleep(0.10)

    if best:
        print(f"\n*** Best candidate: {best} ***")
    else:
        print("\nNo panel-toggle button found in scan area.")

    # ── Step 4: right-click on contact row ──────────────────────────────────
    print("\n[4] Right-clicking contact in list …")
    focus_zalo(hwnd)
    time.sleep(0.3)
    b = grab()
    save(b, "diag3_rc_before.png")
    pyautogui.rightClick(cx, cy)
    time.sleep(0.7)
    a = grab()
    save(a, "diag3_rc_after.png")
    ch = diff_px(b, a)
    print(f"  Pixels changed after right-click: {ch}")
    if ch > 500:
        print("  Context menu appeared (check diag3_rc_after.png)")
    pyautogui.press("escape")
    time.sleep(0.3)

    print("\n" + "=" * 60)
    print("Done.  Review the diag3_*.png files in:")
    print(OUT)
    print("=" * 60)


if __name__ == "__main__":
    main()

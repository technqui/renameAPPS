"""
Zalo Panel Toggle — definitive test
====================================
Tests zx2-220, zy+55 (the position that worked in diag3).
Clears state first (Escape x4), then does a clean before/after screenshot.
"""
import time, os, sys
import pyautogui
from PIL import ImageGrab, Image
import numpy as np
import win32gui, win32con, win32process, win32api
import win32com.client

OUT = r"C:\Users\Admin\Downloads\renameAPPS"
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03


def grab():
    return np.array(ImageGrab.grab())

def save(arr, name):
    Image.fromarray(arr).save(os.path.join(OUT, name))
    print(f"  Saved {name}")

def save_img(img, name):
    img.save(os.path.join(OUT, name))
    print(f"  Saved {name}")

def diff_px(a, b):
    d = np.abs(a.astype(np.int32) - b.astype(np.int32))
    return int((d.max(axis=2) > 15).sum())

def find_zalo():
    my_pid = os.getpid()
    found = []
    def _cb(h, _):
        if not win32gui.IsWindowVisible(h): return
        if "Zalo" not in win32gui.GetWindowText(h): return
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            if pid == my_pid: return
        except Exception: pass
        if win32gui.GetClassName(h) == "Chrome_WidgetWin_1":
            found.append(h)
    win32gui.EnumWindows(_cb, None)
    return found[0] if found else None

def focus_zalo(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    if rect[0] <= -30000 or win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.6)
        rect = win32gui.GetWindowRect(hwnd)
    if win32gui.GetForegroundWindow() == hwnd:
        return rect
    try:
        win32com.client.Dispatch("WScript.Shell").AppActivate(
            win32gui.GetWindowText(hwnd))
        time.sleep(0.35)
    except Exception: pass
    if win32gui.GetForegroundWindow() != hwnd:
        try:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.30)
        except Exception: pass
    return win32gui.GetWindowRect(hwnd)


def main():
    hwnd = find_zalo()
    if not hwnd:
        print("Zalo not found"); return

    rect = focus_zalo(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2-zx, zy2-zy
    print(f"Zalo rect={rect}  size={zw}x{zh}")
    print(f"Focus: {'OK' if win32gui.GetForegroundWindow()==hwnd else 'FAILED'}")

    # ── Clear all open dialogs/panels ─────────────────────────────────────────
    print("\n[0] Clearing state (Esc x5) ...")
    for _ in range(5):
        pyautogui.press("escape")
        time.sleep(0.25)
    time.sleep(0.5)
    save(grab(), "diag6_00_cleared.png")

    # ── Click a contact ───────────────────────────────────────────────────────
    cx = zx + 66 + int(335 * 0.38)
    cy = zy + 208 + 45
    print(f"\n[1] Clicking contact at ({cx}, {cy}) ...")
    pyautogui.click(cx, cy)
    time.sleep(2.0)
    focus_zalo(hwnd)
    time.sleep(0.4)
    before = grab()
    save(before, "diag6_01_before_toggle.png")

    # ── Verify where the cursor lands ─────────────────────────────────────────
    # Capture the header area (right part of window, top rows)
    header_crop = ImageGrab.grab(bbox=(zx + zw//2, zy, zx2, zy + 110))
    save_img(header_crop, "diag6_02_header_area.png")

    # ── Test the known-good position: zx2-220, zy+55 ─────────────────────────
    tx = zx2 - 220
    ty = zy + 55
    print(f"\n[2] Clicking panel toggle at ({tx}, {ty})")
    print(f"    x_rel={tx-zx}, y_rel={ty-zy}, x_from_right={zx2-tx}")

    pyautogui.click(tx, ty)
    time.sleep(1.5)
    focus_zalo(hwnd)
    time.sleep(0.3)
    after = grab()
    save(after, "diag6_03_after_toggle_220.png")
    ch = diff_px(before, after)
    print(f"    Pixels changed: {ch}")
    if ch > 5000:
        print("    SUCCESS — UI changed (panel likely opened or closed)")
    else:
        print("    No significant change")

    # Full header crop after toggle
    header_after = ImageGrab.grab(bbox=(zx + zw//2, zy, zx2, zy + 110))
    save_img(header_after, "diag6_04_header_after_toggle.png")

    # Right side crop (where profile panel would be)
    right_after = ImageGrab.grab(bbox=(zx2-330, zy, zx2, min(zy2, zy+700)))
    save_img(right_after, "diag6_05_right_after_toggle.png")

    # ── Also scan nearby positions ─────────────────────────────────────────────
    print(f"\n[3] Scanning y_rel=45..65, x_from_right=200..240 ...")
    # Reset to clean state
    pyautogui.click(cx, cy)
    time.sleep(1.5)
    focus_zalo(hwnd)

    for y_rel in [45, 50, 55, 60, 65]:
        for x_off in [200, 210, 220, 230, 240]:
            sx = zx2 - x_off
            sy = zy + y_rel
            b = grab()
            pyautogui.click(sx, sy)
            time.sleep(0.55)
            focus_zalo(hwnd)
            time.sleep(0.15)
            a = grab()
            ch2 = diff_px(b, a)
            if ch2 > 3000:
                save(b, f"diag6_scan_{sx}_{sy}_before.png")
                save(a, f"diag6_scan_{sx}_{sy}_after.png")
                print(f"  ({sx},{sy}) [x_off={x_off} y_rel={y_rel}]: {ch2:7d} px ***")
                # toggle back
                pyautogui.click(sx, sy)
                time.sleep(0.5)
            else:
                print(f"  ({sx},{sy}) [x_off={x_off} y_rel={y_rel}]: {ch2:7d} px")
            focus_zalo(hwnd)

    print("\nDone.")

if __name__ == "__main__":
    main()

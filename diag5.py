"""
Zalo Panel Toggle — targeted test
Tries clicking the ☐☐ panel toggle at the correct position:
  x = zx2 - 120  (not -220, which hits the video button)
  y = zy + 50
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
    if win32gui.GetForegroundWindow() == hwnd:
        return win32gui.GetWindowRect(hwnd)
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

def diff_px(a, b):
    d = np.abs(a.astype(np.int32) - b.astype(np.int32))
    return int((d.max(axis=2) > 15).sum())


def main():
    hwnd = find_zalo()
    if not hwnd:
        print("Zalo not found")
        return

    rect = focus_zalo(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2-zx, zy2-zy
    print(f"Zalo rect={rect}  size={zw}x{zh}")
    print(f"Focus: {'OK' if win32gui.GetForegroundWindow()==hwnd else 'FAILED'}")

    # Click first contact
    cx = zx + 66 + int(335 * 0.38)
    cy = zy + 208 + 45
    print(f"\n[1] Click first contact ({cx}, {cy})")
    pyautogui.click(cx, cy)
    time.sleep(1.8)
    focus_zalo(hwnd)
    time.sleep(0.3)

    # Close any open panel: click toggle once to ensure known state
    print("[2] Ensuring panel is CLOSED (toggle once if needed) ...")

    # Try multiple candidate positions for the ☐☐ panel toggle
    # Visual analysis of panel_top: button at ~200px into 310px capture from x=zx2-320
    # → x_abs ≈ zx2-120, y ≈ zy+50
    # Also try nearby positions
    candidates = [
        (zx2 - 120, zy + 50, "zx2-120, zy+50"),
        (zx2 - 115, zy + 52, "zx2-115, zy+52"),
        (zx2 - 125, zy + 48, "zx2-125, zy+48"),
        (zx2 - 110, zy + 55, "zx2-110, zy+55"),
        (zx2 - 130, zy + 50, "zx2-130, zy+50"),
        (zx2 - 100, zy + 50, "zx2-100, zy+50"),
        (zx2 - 140, zy + 50, "zx2-140, zy+50"),
        (zx2 - 150, zy + 50, "zx2-150, zy+50"),
        (zx2 -  90, zy + 50, "zx2-90,  zy+50"),
        (zx2 -  80, zy + 50, "zx2-80,  zy+50"),
    ]

    panel_left = zx2 - 320
    best = None

    for (tx, ty, label) in candidates:
        b = grab()
        pyautogui.click(tx, ty)
        time.sleep(0.7)
        focus_zalo(hwnd)
        time.sleep(0.2)
        a = grab()
        ch = diff_px(b, a)
        print(f"  ({tx}, {ty}) [{label}]: {ch} px changed")
        if ch > 5000:
            save(b, f"diag5_{label.replace(' ','').replace(',','_')}_before.png")
            save(a, f"diag5_{label.replace(' ','').replace(',','_')}_after.png")
            print(f"    *** PANEL TOGGLE CANDIDATE ***")
            if best is None or ch > best[2]:
                best = (tx, ty, ch, label)
            # Toggle back
            pyautogui.click(tx, ty)
            time.sleep(0.6)
            focus_zalo(hwnd)

    if best:
        tx, ty, ch, label = best
        print(f"\nBest: ({tx}, {ty}) [{label}] - {ch} px")
        print(f"  x_rel={tx-zx}, y_rel={ty-zy}")
        print(f"  x_from_right={zx2-tx}, y_from_top={ty-zy}")

        # Now open panel and capture it
        print("\n[3] Opening panel and capturing ...")
        focus_zalo(hwnd)
        time.sleep(0.3)
        pyautogui.click(tx, ty)
        time.sleep(1.5)
        focus_zalo(hwnd)

        # Save full screenshot
        full = grab()
        save(full, "diag5_panel_open_full.png")

        # Capture just the panel area
        img = ImageGrab.grab(bbox=(panel_left, zy, zx2, zy+min(700, zh)))
        img.save(os.path.join(OUT, "diag5_panel_open_crop.png"))
        print("  Saved diag5_panel_open_crop.png")

        # Hover over name area in panel to reveal pencil
        pcx = panel_left + 160
        for py in range(zy+40, zy+180, 12):
            pyautogui.moveTo(pcx, py, duration=0.1)
            time.sleep(0.2)

        hover_img = ImageGrab.grab(bbox=(panel_left, zy, zx2, zy+300))
        hover_img.save(os.path.join(OUT, "diag5_panel_hover.png"))
        print("  Saved diag5_panel_hover.png")
    else:
        print("\nNo candidate found in this range.")
        # Save full screenshot for inspection
        save(grab(), "diag5_no_candidate.png")

    print("\nDone.")


if __name__ == "__main__":
    main()

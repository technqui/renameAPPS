"""
Zalo Panel Diagnostic v4
========================
1. Opens profile panel at the correct toggle position (zx2-220, zy+55).
2. Saves a zoomed screenshot of just the right profile panel.
3. Tries scrolling the profile panel to find the nickname section.
4. Saves multiple panel states.

Run:  python diag4.py
"""

import time, os, sys
import pyautogui

try:
    from PIL import ImageGrab, Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    print("ERROR: Pillow not installed.")
    sys.exit(1)

try:
    import win32gui, win32con, win32process, win32api
    import win32com.client
except ImportError:
    print("ERROR: pywin32 not installed.")
    sys.exit(1)

OUT = r"C:\Users\Admin\Downloads\renameAPPS"
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03


def grab_region(x, y, w, h):
    return ImageGrab.grab(bbox=(x, y, x + w, y + h))


def save_img(img, name):
    path = os.path.join(OUT, name)
    img.save(path)
    print(f"  Saved {name}")
    return path


def find_zalo():
    my_pid = os.getpid()
    found = []
    def _cb(h, _):
        if not win32gui.IsWindowVisible(h): return
        title = win32gui.GetWindowText(h)
        if "Zalo" not in title: return
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            if pid == my_pid: return
        except Exception: pass
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
    try:
        title = win32gui.GetWindowText(hwnd)
        win32com.client.Dispatch("WScript.Shell").AppActivate(title)
        time.sleep(0.35)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception:
        pass
    try:
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32gui.SetForegroundWindow(hwnd)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.30)
        if win32gui.GetForegroundWindow() == hwnd:
            return True
    except Exception:
        pass
    return win32gui.GetForegroundWindow() == hwnd


def main():
    print("=" * 60)
    print("Zalo Panel Diagnostic v4 — Nickname field location")
    print("=" * 60)

    hwnd = find_zalo()
    if not hwnd:
        print("ERROR: Zalo not found.")
        return

    rect = win32gui.GetWindowRect(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2 - zx, zy2 - zy
    print(f"Zalo hwnd={hwnd}  rect={rect}  size={zw}x{zh}")

    # Restore if minimized before reading rect
    if win32gui.IsIconic(hwnd) or rect[0] <= -30000:
        print("Zalo is minimized — restoring...")
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.6)
        rect = win32gui.GetWindowRect(hwnd)
        zx, zy, zx2, zy2 = rect
        zw, zh = zx2 - zx, zy2 - zy
        print(f"Restored rect: {rect}  size={zw}x{zh}")

    ok = focus_zalo(hwnd)
    print(f"Focus: {'OK' if ok else 'FAILED'}")
    if not ok:
        print("Zalo not focused — cannot proceed.")
        return
    # Re-read rect after focus (window might have been restored)
    rect = win32gui.GetWindowRect(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2 - zx, zy2 - zy
    print(f"Final rect: {rect}  size={zw}x{zh}")
    if zx <= -30000:
        print("ERROR: Still getting -32000 rect after restore. Aborting.")
        return
    time.sleep(0.4)

    # ── Close any open panel first ────────────────────────────────────────────
    panel_toggle_x = zx2 - 220
    panel_toggle_y = zy + 55
    print(f"\nPanel toggle position: ({panel_toggle_x}, {panel_toggle_y})")
    print(f"  relative to window:  x_rel={panel_toggle_x-zx}, y_rel={panel_toggle_y-zy}")

    # ── Click first contact ───────────────────────────────────────────────────
    cx = zx + 66 + int(335 * 0.38)
    cy = zy + 208 + 45
    print(f"\n[1] Clicking first contact at ({cx}, {cy}) ...")
    pyautogui.click(cx, cy)
    time.sleep(1.8)
    focus_zalo(hwnd)
    time.sleep(0.3)
    save_img(ImageGrab.grab(), "diag4_01_contact_clicked.png")

    # ── Ensure panel is CLOSED, then open it ─────────────────────────────────
    # Take a snapshot of the right side to check state
    right_w = 400
    right_snap_before = grab_region(zx2 - right_w, zy, right_w, zh)
    save_img(right_snap_before, "diag4_02_right_before_toggle.png")

    print(f"\n[2] Clicking panel toggle at ({panel_toggle_x}, {panel_toggle_y}) ...")
    pyautogui.click(panel_toggle_x, panel_toggle_y)
    time.sleep(1.2)
    focus_zalo(hwnd)
    time.sleep(0.3)

    right_snap_after = grab_region(zx2 - right_w, zy, right_w, zh)
    save_img(right_snap_after, "diag4_03_right_after_toggle.png")

    # Full screenshot
    save_img(ImageGrab.grab(), "diag4_04_full_after_toggle.png")

    # Check if panel opened (right side changed)
    before_arr = np.array(right_snap_before)
    after_arr  = np.array(right_snap_after)
    diff = np.abs(before_arr.astype(np.int32) - after_arr.astype(np.int32))
    changed = int((diff.max(axis=2) > 15).sum())
    print(f"    Right-side pixels changed: {changed}")

    if changed < 1000:
        print("    Panel did NOT open — trying once more (might have closed it).")
        pyautogui.click(panel_toggle_x, panel_toggle_y)
        time.sleep(1.2)
        focus_zalo(hwnd)
        save_img(ImageGrab.grab(), "diag4_05_full_retry_toggle.png")
        right_snap_after = grab_region(zx2 - right_w, zy, right_w, zh)
        save_img(right_snap_after, "diag4_06_right_retry_toggle.png")

    # ── Capture panel at multiple scroll positions ────────────────────────────
    # The profile panel should be on the right side.
    # Profile panel typically occupies the right ~300-320px of the window.
    panel_left = zx2 - 320
    panel_width = 310

    print(f"\n[3] Capturing profile panel (x={panel_left}..{panel_left+panel_width}) ...")

    # Scroll position 1: top
    panel_top = grab_region(panel_left, zy, panel_width, min(600, zh))
    save_img(panel_top, "diag4_07_panel_top.png")

    # Move mouse INTO the panel and scroll down a bit
    panel_centre_x = panel_left + panel_width // 2
    panel_centre_y = zy + zh // 2

    print(f"    Moving mouse to panel centre ({panel_centre_x}, {panel_centre_y})")
    pyautogui.moveTo(panel_centre_x, panel_centre_y, duration=0.2)
    time.sleep(0.2)

    # Scroll down 3 ticks
    pyautogui.scroll(-3)
    time.sleep(0.5)
    panel_scroll1 = grab_region(panel_left, zy, panel_width, min(600, zh))
    save_img(panel_scroll1, "diag4_08_panel_scroll1.png")

    # Scroll down 3 more ticks
    pyautogui.scroll(-3)
    time.sleep(0.5)
    panel_scroll2 = grab_region(panel_left, zy, panel_width, min(600, zh))
    save_img(panel_scroll2, "diag4_09_panel_scroll2.png")

    # Full window after scroll
    save_img(ImageGrab.grab(), "diag4_10_full_scrolled.png")

    # Scroll back to top
    pyautogui.scroll(10)
    time.sleep(0.4)
    panel_top2 = grab_region(panel_left, zy, panel_width, min(600, zh))
    save_img(panel_top2, "diag4_11_panel_top_again.png")

    # ── Move mouse over contact name area and hover ───────────────────────────
    # The nickname / name area in the panel is typically in the top 200px
    # Try hovering at multiple y positions within the panel to reveal pencil icon
    print("\n[4] Hovering over panel name area to reveal edit (pencil) icon ...")
    for y_offset in range(60, 200, 15):
        hover_y = zy + y_offset
        pyautogui.moveTo(panel_centre_x, hover_y, duration=0.15)
        time.sleep(0.30)

    # Save what's visible after hovering
    save_img(grab_region(panel_left, zy, panel_width, 300), "diag4_12_panel_hover.png")
    save_img(ImageGrab.grab(), "diag4_13_full_hover.png")

    print("\n" + "=" * 60)
    print("Done.  Check diag4_*.png files in:")
    print(OUT)
    print("=" * 60)


if __name__ == "__main__":
    main()

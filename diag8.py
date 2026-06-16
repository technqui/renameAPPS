"""
Zalo Profile Panel — nickname field finder
==========================================
1. Opens the profile panel at the confirmed position (zx2-100, zy+50).
2. Captures the panel at high resolution.
3. Hovers over the name area to reveal the pencil icon and captures it.
4. Clicks the pencil and reads the current nickname via clipboard.

This gives us the exact coordinates for the nickname edit workflow.
"""
import time, os
import pyautogui, pyperclip
from PIL import ImageGrab, Image
import numpy as np
import win32gui, win32con, win32process, win32api
import win32com.client

OUT = r"C:\Users\Admin\Downloads\renameAPPS"
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03

def grab():           return np.array(ImageGrab.grab())
def diff(a,b):
    d = np.abs(a.astype(np.int32)-b.astype(np.int32))
    return int((d.max(axis=2)>15).sum())
def save_img(img, name):
    img.save(os.path.join(OUT, name)); print(f"  Saved {name}")
def save_arr(arr, name):
    Image.fromarray(arr).save(os.path.join(OUT, name)); print(f"  Saved {name}")

def find_zalo():
    my_pid = os.getpid(); found = []
    def _cb(h,_):
        if not win32gui.IsWindowVisible(h): return
        if "Zalo" not in win32gui.GetWindowText(h): return
        try:
            _,pid = win32process.GetWindowThreadProcessId(h)
            if pid == my_pid: return
        except: pass
        if win32gui.GetClassName(h)=="Chrome_WidgetWin_1": found.append(h)
    win32gui.EnumWindows(_cb,None)
    return found[0] if found else None

def focus(hwnd):
    r = win32gui.GetWindowRect(hwnd)
    if r[0]<=-30000 or win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE); time.sleep(0.6)
    if win32gui.GetForegroundWindow()==hwnd: return win32gui.GetWindowRect(hwnd)
    try:
        win32com.client.Dispatch("WScript.Shell").AppActivate(
            win32gui.GetWindowText(hwnd)); time.sleep(0.35)
    except: pass
    if win32gui.GetForegroundWindow()!=hwnd:
        try:
            win32api.keybd_event(win32con.VK_MENU,0,0,0)
            win32gui.SetForegroundWindow(hwnd)
            win32api.keybd_event(win32con.VK_MENU,0,win32con.KEYEVENTF_KEYUP,0)
            time.sleep(0.30)
        except: pass
    return win32gui.GetWindowRect(hwnd)

def main():
    hwnd = find_zalo()
    if not hwnd: print("Zalo not found"); return
    rect = focus(hwnd)
    zx, zy, zx2, zy2 = rect
    zw, zh = zx2-zx, zy2-zy
    print(f"rect={rect} size={zw}x{zh}")

    # Clear state
    for _ in range(5): pyautogui.press("escape"); time.sleep(0.2)
    time.sleep(0.5); focus(hwnd)

    # Click first contact
    cx = zx + 66 + int(335*0.38)
    cy = zy + 208 + 45
    print(f"\n[1] Click contact ({cx},{cy})")
    pyautogui.click(cx, cy); time.sleep(2.0); focus(hwnd); time.sleep(0.3)

    # Open profile panel
    tx = zx2 - 100
    ty = zy + 50
    print(f"[2] Open profile panel ({tx},{ty})")
    b = grab()
    pyautogui.click(tx, ty); time.sleep(1.8); focus(hwnd); time.sleep(0.3)
    a = grab()
    ch = diff(b, a)
    print(f"    Pixels changed: {ch}")
    if ch < 5000:
        print("    Panel may not have opened. Trying again...")
        pyautogui.click(tx, ty); time.sleep(1.8); focus(hwnd); time.sleep(0.3)

    save_arr(grab(), "diag8_01_panel_open.png")

    # Capture just the panel area
    panel_w = 320
    panel_x = zx2 - panel_w
    panel_img = ImageGrab.grab(bbox=(panel_x, zy, zx2, zy2))
    save_img(panel_img, "diag8_02_panel_full.png")

    # Capture just the top 300px of the panel
    top_img = ImageGrab.grab(bbox=(panel_x, zy, zx2, zy+300))
    save_img(top_img, "diag8_03_panel_top300.png")

    # ── Hover over name area to reveal pencil icon ────────────────────────────
    # Name area is typically in the top portion of the panel, roughly y_rel=100-170
    panel_cx = panel_x + panel_w // 2    # horizontal centre of panel
    print(f"\n[3] Hovering over name area (panel centre x={panel_cx}) ...")

    best_pencil_y = None
    prev_hover = grab()
    for y_abs in range(zy+90, zy+200, 8):
        pyautogui.moveTo(panel_cx, y_abs, duration=0.08)
        time.sleep(0.30)
        cur = grab()
        ch2 = diff(prev_hover, cur)
        if ch2 > 300:
            print(f"  hover at y_abs={y_abs} (y_rel={y_abs-zy}): {ch2} px changed")
            if best_pencil_y is None:
                best_pencil_y = y_abs
        prev_hover = cur

    # Save hover state at the best y
    if best_pencil_y:
        print(f"\n  Best hover y: {best_pencil_y} (y_rel={best_pencil_y-zy})")
        pyautogui.moveTo(panel_cx, best_pencil_y, duration=0.1)
        time.sleep(0.5)
        hover_img = ImageGrab.grab(bbox=(panel_x, zy, zx2, zy+300))
        save_img(hover_img, "diag8_04_name_hover.png")
    else:
        # Try hovering at a range and capture
        print("  No significant hover change found. Saving hover at y_rel=130,140,150...")
        for y_rel in [130, 140, 150]:
            pyautogui.moveTo(panel_cx, zy+y_rel, duration=0.1)
            time.sleep(0.4)
        hover_img = ImageGrab.grab(bbox=(panel_x, zy, zx2, zy+300))
        save_img(hover_img, "diag8_04_name_hover.png")

    # Save crop of panel top after hovering (may show pencil)
    final_top = ImageGrab.grab(bbox=(panel_x, zy, zx2, zy+300))
    save_img(final_top, "diag8_05_panel_top_hover_final.png")

    # ── Scan for pencil icon click ─────────────────────────────────────────────
    # Pencil icon appears to the RIGHT of the name text
    # Try clicking in the right portion of the panel name area
    print(f"\n[4] Trying to click name edit (pencil area) ...")
    # Hover first to make pencil visible
    if best_pencil_y:
        hover_y = best_pencil_y
    else:
        hover_y = zy + 140

    for attempt in range(3):
        pyautogui.moveTo(panel_cx, hover_y, duration=0.1)
        time.sleep(0.5)

        # Try clicking to the right of centre (where pencil would appear)
        for pencil_x in [panel_cx + 60, panel_cx + 80, panel_cx + 40,
                         panel_cx + 100, panel_cx + 20, panel_cx]:
            pyautogui.click(pencil_x, hover_y)
            time.sleep(0.6); focus(hwnd); time.sleep(0.2)
            pyperclip.copy("\x00")
            pyautogui.hotkey("ctrl","a"); time.sleep(0.15)
            pyautogui.hotkey("ctrl","c"); time.sleep(0.25)
            got = pyperclip.paste()
            if got != "\x00":
                print(f"  Edit field activated at ({pencil_x},{hover_y})")
                print(f"  Current content: {got!r}")
                # Save state
                save_arr(grab(), f"diag8_06_edit_active.png")
                # Close without saving
                pyautogui.press("escape"); time.sleep(0.3)
                print(f"\nNickname edit position found:")
                print(f"  x_rel={pencil_x-zx}, y_rel={hover_y-zy}")
                print(f"  x_from_right={zx2-pencil_x}, y_from_top={hover_y-zy}")
                return
            pyautogui.press("escape"); time.sleep(0.2)

    save_arr(grab(), "diag8_07_no_edit.png")
    print("Could not activate the nickname edit field.")
    print("Check diag8_*.png files for the panel layout.")

if __name__ == "__main__":
    main()

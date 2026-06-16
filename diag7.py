"""
Zalo Panel Toggle — fine scan around zx2-60..zx2-50
The search (magnifier) opens at zx2-80. The panel toggle (two rectangles)
must be the NEXT button to the right — so zx2-60 to zx2-40.
Also tests a wide grid at the correct y range (y_rel 44-64).
"""
import time, os
import pyautogui
from PIL import ImageGrab, Image
import numpy as np
import win32gui, win32con, win32process, win32api
import win32com.client

OUT = r"C:\Users\Admin\Downloads\renameAPPS"
pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.03

def grab():           return np.array(ImageGrab.grab())
def diff(a, b):
    d = np.abs(a.astype(np.int32)-b.astype(np.int32))
    return int((d.max(axis=2)>15).sum())

def save(arr, name):
    Image.fromarray(arr).save(os.path.join(OUT, name))
    print(f"  Saved {name}")

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

def close_panels(hwnd):
    for _ in range(6):
        pyautogui.press("escape"); time.sleep(0.20)
    time.sleep(0.5)

def click_contact(zx, zy):
    cx = zx + 66 + int(335*0.38)
    cy = zy + 208 + 45
    pyautogui.click(cx, cy)
    time.sleep(2.0)

def main():
    hwnd = find_zalo()
    if not hwnd: print("Zalo not found"); return
    rect = focus(hwnd)
    zx, zy, zx2, zy2 = rect
    print(f"rect={rect}")
    print(f"Focus: {'OK' if win32gui.GetForegroundWindow()==hwnd else 'FAIL'}")

    close_panels(hwnd)
    focus(hwnd)

    click_contact(zx, zy)
    focus(hwnd); time.sleep(0.3)
    save(grab(), "diag7_00_contact_open.png")

    # ── Tight scan: zx2-70 to zx2-35, y_rel=44..64 ───────────────────────────
    # 🔍 search is at zx2-80; ☐☐ panel toggle should be to the right of it
    print("\nScanning zx2-70..zx2-35, y_rel=44..64 (step 4px) ...")
    print(f"(absolute y range: {zy+44}..{zy+64})")

    best = None

    for y_rel in range(44, 65, 4):
        for x_off in range(35, 71, 3):   # x_from_right: 35..70
            sx = zx2 - x_off
            sy = zy + y_rel
            b = grab()
            pyautogui.click(sx, sy)
            time.sleep(0.55)
            focus(hwnd); time.sleep(0.15)
            a = grab()
            ch = diff(b, a)
            flag = ""
            if ch > 50000:
                flag = " *** BIG ***"
                save(b, f"diag7_{sx}_{sy}_before.png")
                save(a, f"diag7_{sx}_{sy}_after.png")
                pyautogui.click(sx, sy)   # toggle back
                time.sleep(0.5)
                focus(hwnd)
                if best is None or ch > best[2]:
                    best = (sx, sy, ch)
            elif ch > 3000:
                flag = " *"
            print(f"  ({sx},{sy}) off={x_off} y_rel={y_rel}: {ch:8d} px{flag}")
        focus(hwnd)

    # ── Also try the wider range at y_rel=50 and 55 ───────────────────────────
    print("\nWide scan at y_rel=50 and y_rel=55, x_off=35..250 ...")
    close_panels(hwnd); focus(hwnd)
    click_contact(zx, zy); focus(hwnd); time.sleep(0.3)

    for y_rel in [50, 55]:
        for x_off in range(35, 251, 5):
            sx = zx2 - x_off
            sy = zy + y_rel
            b = grab()
            pyautogui.click(sx, sy)
            time.sleep(0.5)
            focus(hwnd); time.sleep(0.12)
            a = grab()
            ch = diff(b, a)
            flag = ""
            if ch > 50000:
                flag = " *** BIG ***"
                save(b, f"diag7_wide_{sx}_{sy}_before.png")
                save(a, f"diag7_wide_{sx}_{sy}_after.png")
                pyautogui.click(sx, sy)
                time.sleep(0.5); focus(hwnd)
                if best is None or ch > best[2]:
                    best = (sx, sy, ch)
            elif ch > 3000:
                flag = " *"
            if ch > 0 or x_off % 20 == 0:
                print(f"  ({sx},{sy}) off={x_off} y_rel={y_rel}: {ch:8d} px{flag}")

    print(f"\nBest: {best}")
    print("Done.")

if __name__ == "__main__":
    main()

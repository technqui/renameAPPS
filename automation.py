"""
Zalo Contact Renamer — Automation Engine
"""

import ctypes
import ctypes.wintypes
import os
import re
import threading
import time
from typing import Callable, List, Optional, Tuple

import pyautogui
import pyperclip

try:
    import win32gui, win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from PIL import ImageGrab
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from config_manager import Config, TPL_INFO, TPL_NICK_LBL, TPL_NICK_ICON
from tracker import ContactTracker
from log_manager import LogManager

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.04

# Sentinel that survives Windows clipboard round-trips (unlike "\x00")
_SENTINEL = "##ZNR_SENTINEL_9x7##"

# ── Win32 message constants ───────────────────────────────────────────────────
_WM_LBUTTONDOWN = 0x0201
_WM_LBUTTONUP   = 0x0202
_WM_MOUSEWHEEL  = 0x020A
_WM_KEYDOWN     = 0x0100
_WM_KEYUP       = 0x0101
_MK_LBUTTON     = 0x0001
_WHEEL_DOWN     = ((-120) & 0xFFFF) << 16   # one notch down, high-word of wParam
_WHEEL_UP       = ( 120  & 0xFFFF) << 16   # one notch up

_VK_RETURN  = 0x0D
_VK_ESCAPE  = 0x1B
_VK_CONTROL = 0x11
_VK_A       = 0x41
_VK_C       = 0x43
_VK_V       = 0x56


# ── Template-matching helper ─────────────────────────────────────────────────

def find_template(
    path: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    confidence: float = 0.72,
) -> Optional[Tuple[int, int]]:
    """Locate *path* on screen; return centre (x, y) or None."""
    if not os.path.exists(path):
        return None
    try:
        loc = pyautogui.locateOnScreen(path, region=region, confidence=confidence)
        if loc:
            return (int(loc.left + loc.width  // 2),
                    int(loc.top  + loc.height // 2))
    except Exception:
        pass
    return None


# ── Main automation class ────────────────────────────────────────────────────

class ZaloAutomation:

    def __init__(
        self,
        config:       Config,
        tracker:      ContactTracker,
        log_manager:  LogManager,
        log_cb:       Callable[[str], None] = print,
        progress_cb:  Callable[[int], None] = lambda n: None,
        status_cb:    Callable[[str], None] = lambda s: None,
    ):
        self.cfg      = config
        self.tracker  = tracker
        self.log_mgr  = log_manager
        self.log      = log_cb
        self.progress = progress_cb
        self.status   = status_cb

        self._pause = threading.Event();  self._pause.set()
        self._stop  = threading.Event()

        self._cur_num:    int = config.start_number
        self._seen_names: set = set()

        self.zalo_hwnd: Optional[int]                    = None
        self.zalo_rect: Optional[Tuple[int,int,int,int]] = None
        self._filter_fingerprint: Optional[np.ndarray]  = None

    # ── Window helpers ────────────────────────────────────────────────────────

    @staticmethod
    def find_zalo_hwnd() -> Optional[int]:
        if not HAS_WIN32:
            return None
        import os as _os
        try:
            import win32process
            my_pid = _os.getpid()
        except Exception:
            my_pid = -1

        electron: List[int] = []
        other:    List[int] = []

        def _cb(h, _):
            if not win32gui.IsWindowVisible(h):
                return
            if "Zalo" not in win32gui.GetWindowText(h):
                return
            try:
                _, pid = win32process.GetWindowThreadProcessId(h)
                if pid == my_pid:
                    return
            except Exception:
                pass
            if win32gui.GetClassName(h) == "Chrome_WidgetWin_1":
                electron.append(h)
            else:
                other.append(h)

        win32gui.EnumWindows(_cb, None)
        candidates = electron or other
        return candidates[0] if candidates else None

    def find_zalo_window(self) -> bool:
        h = self.find_zalo_hwnd()
        if not h:
            self.log("ERROR: Zalo PC not found. Please open Zalo first.")
            return False
        self.zalo_hwnd = h
        if win32gui.IsIconic(h):
            # Do NOT restore a minimised Electron window automatically.
            # Restoring it forces a full UI re-render that clears the active
            # search / filter.  Require the user to keep Zalo visible.
            self.log("ERROR: Zalo is minimised — please restore it manually "
                     "(with your search/filter still active) before starting.")
            return False
        self.zalo_rect = win32gui.GetWindowRect(h)
        self.log(f"Zalo window: rect={self.zalo_rect}")
        return True

    def _refresh_rect(self):
        if HAS_WIN32 and self.zalo_hwnd:
            try:
                rect = win32gui.GetWindowRect(self.zalo_hwnd)
                if rect[0] > -30000:
                    self.zalo_rect = rect
            except Exception:
                pass

    def _focus_zalo(self):
        """
        Bring Zalo to the foreground without sending any keyboard events.

        The old implementation sent a bare Alt keydown/up pair (the
        "VK_MENU trick") to satisfy Windows' SetForegroundWindow lock.
        After SetForegroundWindow the focus has already moved to Zalo, so
        the Alt-up event lands on Zalo — which Electron interprets as a
        menu-bar activation, clearing the active search/filter.

        We use AttachThreadInput instead: it lets a background thread call
        SetForegroundWindow legally with zero keyboard events.
        """
        if not HAS_WIN32 or not self.zalo_hwnd:
            return
        hwnd = self.zalo_hwnd
        try:
            if win32gui.IsIconic(hwnd):
                # Do not restore — see find_zalo_window for the reason.
                return
            if win32gui.GetForegroundWindow() == hwnd:
                return

            # Primary: attach to the foreground thread so Windows allows the
            # SetForegroundWindow call without any keyboard event injection.
            try:
                import win32process, win32api
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
                    time.sleep(0.20)
                    if win32gui.GetForegroundWindow() == hwnd:
                        return
            except Exception:
                pass

            # Fallback: direct call (works when already on the UI thread or
            # when Windows' foreground-lock is not active).
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.20)
        except Exception:
            pass

    # ── Background-mode window save/restore ───────────────────────────────────

    def _save_fg(self) -> Optional[int]:
        if not HAS_WIN32 or not self.cfg.background_mode:
            return None
        try:
            h = win32gui.GetForegroundWindow()
            return h if h != self.zalo_hwnd else None
        except Exception:
            return None

    def _restore_fg(self, hwnd: Optional[int]):
        if not hwnd or not HAS_WIN32 or not self.cfg.background_mode:
            return
        try:
            if not win32gui.IsWindow(hwnd):
                return
            time.sleep(0.12)
            try:
                import win32process, win32api
                fg = win32gui.GetForegroundWindow()
                if fg and fg != hwnd:
                    fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
                    my_tid = win32api.GetCurrentThreadId()
                    win32process.AttachThreadInput(fg_tid, my_tid, True)
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    finally:
                        win32process.AttachThreadInput(fg_tid, my_tid, False)
                    return
            except Exception:
                pass
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _zalo_region(self, x0_pct, y0_pct, x1_pct, y1_pct
                     ) -> Optional[Tuple[int,int,int,int]]:
        """Return (left, top, width, height) search region in screen coordinates."""
        if not self.zalo_rect:
            return None
        zx, zy, zx2, zy2 = self.zalo_rect
        zw, zh = zx2 - zx, zy2 - zy
        x = zx + int(zw * x0_pct);  y = zy + int(zh * y0_pct)
        w = int(zw * (x1_pct - x0_pct));  h = int(zh * (y1_pct - y0_pct))
        return (x, y, w, h)

    def _contact_click_x(self) -> int:
        if not self.cfg.contact_region or not self.zalo_rect:
            return 0
        rx, ry, rw, _ = self.cfg.contact_region
        return self.zalo_rect[0] + rx + int(rw * 0.38)

    def _row_positions(self) -> List[int]:
        if not self.cfg.contact_region or not self.cfg.contact_item_height:
            return []
        if not self.zalo_rect or self.zalo_rect[0] < -30000:
            return []
        _, ry, _, rh = self.cfg.contact_region
        top = self.zalo_rect[1] + ry
        h   = self.cfg.contact_item_height
        rows = []
        y = top + h // 2
        while y < top + rh - h // 3:
            rows.append(y)
            y += h
        return rows

    def _abs_contact_region(self) -> Optional[List[int]]:
        if not self.cfg.contact_region or not self.zalo_rect:
            return None
        rx, ry, rw, rh = self.cfg.contact_region
        return [self.zalo_rect[0] + rx, self.zalo_rect[1] + ry, rw, rh]

    # ── Screenshot helpers ────────────────────────────────────────────────────

    def _grab(self, region: Optional[List[int]] = None):
        if not HAS_PIL:
            return None
        try:
            if region:
                ax, ay, aw, ah = region
                img = ImageGrab.grab(bbox=(ax, ay, ax + aw, ay + ah))
            else:
                img = ImageGrab.grab()
            return np.array(img)
        except Exception:
            return None

    def _similar(self, a, b, threshold: float = 0.992) -> bool:
        if a is None or b is None:
            return False
        if a.shape != b.shape:
            return False
        diff = np.abs(a.astype(np.int32) - b.astype(np.int32))
        return (1.0 - diff.sum() / (a.size * 255)) >= threshold

    # ── Background window interaction (no physical cursor / no focus steal) ────
    #
    # All methods below interact directly with the Zalo render HWND via Win32
    # PostMessage, which delivers mouse and keyboard events without:
    #   • moving the physical cursor
    #   • calling SetForegroundWindow (no visual focus steal)
    #   • intercepting the user's own keyboard or mouse
    #
    # _bg_set_focus() is the only call that touches keyboard routing.  It uses
    # AttachThreadInput + SetFocus (NOT SetForegroundWindow) so the user's active
    # window keeps its highlighted title bar; only the keyboard pipe is briefly
    # redirected while a Ctrl+C / Ctrl+V is injected.

    def _find_render_hwnd(self) -> Optional[int]:
        """Return the Chrome_RenderWidgetHostHWND child of the Zalo main window."""
        if not HAS_WIN32 or not self.zalo_hwnd:
            return None
        found: List[int] = []
        def _cb(h, _):
            try:
                if win32gui.GetClassName(h) == "Chrome_RenderWidgetHostHWND":
                    found.append(h)
            except Exception:
                pass
        try:
            win32gui.EnumChildWindows(self.zalo_hwnd, _cb, None)
        except Exception:
            pass
        return found[0] if found else None

    @staticmethod
    def _screen_to_client(hwnd: int, sx: int, sy: int) -> tuple:
        pt = ctypes.wintypes.POINT(sx, sy)
        ctypes.windll.user32.ScreenToClient(hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    @staticmethod
    def _make_lp(cx: int, cy: int) -> int:
        return ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)

    def _bg_click(self, sx: int, sy: int):
        """
        Left-click at screen position (sx, sy) by posting messages directly to
        the Zalo render HWND.  The physical mouse cursor does not move.
        Falls back to pyautogui.click if win32 is unavailable.
        """
        if not HAS_WIN32:
            pyautogui.click(sx, sy)
            return
        h = self._find_render_hwnd() or self.zalo_hwnd
        if not h:
            pyautogui.click(sx, sy)
            return
        try:
            cx, cy = self._screen_to_client(h, sx, sy)
            lp = self._make_lp(cx, cy)
            win32gui.PostMessage(h, _WM_LBUTTONDOWN, _MK_LBUTTON, lp)
            time.sleep(0.06)
            win32gui.PostMessage(h, _WM_LBUTTONUP, 0, lp)
        except Exception:
            pyautogui.click(sx, sy)

    def _bg_scroll(self, sx: int, sy: int, duration: float, direction: int = -1):
        """
        Send wheel-scroll events to the Zalo render HWND for 'duration' seconds.
        direction: -1 = down (show more contacts), +1 = up.
        The physical cursor does not move.
        Falls back to pyautogui.scroll if win32 is unavailable.
        """
        interval = max(0.02, 1.0 / max(1.0, self.cfg.scroll_speed))
        wp = _WHEEL_DOWN if direction < 0 else _WHEEL_UP
        if not HAS_WIN32 or not self.zalo_hwnd:
            d = -1 if direction < 0 else 1
            deadline = time.time() + duration
            while time.time() < deadline:
                pyautogui.scroll(d)
                time.sleep(interval)
            return
        h = self._find_render_hwnd() or self.zalo_hwnd
        lp = self._make_lp(sx, sy)
        deadline = time.time() + duration
        try:
            while time.time() < deadline:
                win32gui.PostMessage(h, _WM_MOUSEWHEEL, wp, lp)
                time.sleep(interval)
        except Exception:
            pass

    def _bg_set_focus(self):
        """
        Give Zalo's render HWND keyboard focus WITHOUT calling SetForegroundWindow.
        The user's window keeps its visual 'active' titlebar; only the OS keyboard
        pipe is redirected to Zalo.

        Correct pattern: AttachThreadInput(zalo_tid, my_tid) so our thread can
        call SetFocus on a window owned by Zalo's message-queue thread.
        """
        if not HAS_WIN32 or not self.zalo_hwnd:
            return
        h = self._find_render_hwnd() or self.zalo_hwnd
        try:
            import win32process, win32api
            zalo_tid = win32process.GetWindowThreadProcessId(h)[0]
            my_tid   = win32api.GetCurrentThreadId()
            if zalo_tid != my_tid:
                win32process.AttachThreadInput(zalo_tid, my_tid, True)
                try:
                    ctypes.windll.user32.SetFocus(h)
                finally:
                    win32process.AttachThreadInput(zalo_tid, my_tid, False)
            else:
                ctypes.windll.user32.SetFocus(h)
            time.sleep(0.06)
        except Exception:
            pass

    def _restore_keyboard_focus(self):
        """
        Return keyboard focus to the current foreground window after each keyboard
        operation so the user's own keystrokes are not silently swallowed by Zalo
        between automation steps.
        """
        if not HAS_WIN32:
            return
        try:
            import win32process, win32api
            fg = win32gui.GetForegroundWindow()
            if not fg or fg == self.zalo_hwnd:
                return
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
            my_tid = win32api.GetCurrentThreadId()
            win32process.AttachThreadInput(fg_tid, my_tid, True)
            try:
                ctypes.windll.user32.SetFocus(fg)
            finally:
                win32process.AttachThreadInput(fg_tid, my_tid, False)
        except Exception:
            pass

    def _bg_hotkey(self, *vks: int):
        """
        Inject a key combination into Zalo.

        WHY NOT PostMessage:
          PostMessage(WM_KEYDOWN) does NOT update GetKeyState().  Chromium calls
          GetKeyState(VK_CONTROL) when it receives WM_KEYDOWN(VK_C) to decide
          whether this is Ctrl+C or a plain 'c'.  With PostMessage the state is
          always 0, so every modifier is ignored and the bare character gets typed
          directly into the chat — producing the "ccaavv" bug.

        FIX:
          SetFocus (no SetForegroundWindow, no visual titlebar change) then
          pyautogui.hotkey which calls SendInput.  SendInput updates GetKeyState,
          so Chromium correctly sees VK_CONTROL as held and fires the shortcut.
          Keyboard focus is restored to the user's window immediately after.
        """
        _map = {_VK_CONTROL: "ctrl", _VK_A: "a", _VK_C: "c",
                _VK_V: "v", _VK_RETURN: "enter", _VK_ESCAPE: "escape"}
        keys = [_map.get(v, chr(v).lower()) for v in vks]

        if HAS_WIN32:
            self._bg_set_focus()
        try:
            pyautogui.hotkey(*keys)
        except Exception:
            pass
        if HAS_WIN32:
            self._restore_keyboard_focus()

    def _bg_press(self, vk: int):
        """
        Press a single key in Zalo via SetFocus + SendInput (same reason as
        _bg_hotkey — PostMessage alone fails for Chromium keyboard shortcuts).
        """
        _map = {_VK_RETURN: "enter", _VK_ESCAPE: "escape"}
        key = _map.get(vk, chr(vk).lower())

        if HAS_WIN32:
            self._bg_set_focus()
        try:
            pyautogui.press(key)
        except Exception:
            pass
        if HAS_WIN32:
            self._restore_keyboard_focus()

    def _bg_select_paste(self):
        """
        Ctrl+A then Ctrl+V in ONE focus operation, without releasing Zalo's
        keyboard focus between the two keystrokes.

        WHY THIS IS NEEDED:
          If _bg_hotkey(Ctrl+A) and _bg_hotkey(Ctrl+V) are called separately,
          _restore_keyboard_focus() runs between them.  Chromium clears the
          text-field selection when the render widget loses keyboard focus, so
          by the time Ctrl+V fires the selection is gone and the paste appends
          instead of replacing — producing e.g. "John SmithKH566 John Smith".
          Holding focus across both keystrokes keeps the selection intact.
        """
        if HAS_WIN32:
            self._bg_set_focus()
        try:
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "v")
        except Exception:
            pass
        if HAS_WIN32:
            self._restore_keyboard_focus()

    # ── Scroll speed measurement ──────────────────────────────────────────────

    def _find_scroll_shift(self, before: np.ndarray, after: np.ndarray) -> Optional[int]:
        """
        Measure how many pixels the contact list scrolled upward between two
        screenshots of the same region.

        Strategy: the top rows of 'after' must have been visible somewhere in
        the upper half of 'before' before the scroll.  Slide a reference strip
        (top of 'after') down through 'before' and find the position with the
        lowest mean absolute difference — that y-offset is the scroll shift.

        Returns pixel shift (>0) or None when the match is not confident.
        """
        if not HAS_PIL or before is None or after is None:
            return None
        if before.shape != after.shape:
            return None

        h = before.shape[0]
        row_h = max(self.cfg.contact_item_height or 40, 20)
        ref_h = min(row_h * 2, h // 4)     # reference strip ≈ 2 rows, max ¼ frame
        if ref_h < 10:
            return None

        ref = after[:ref_h, :, :].astype(np.float32)

        best_diff  = float('inf')
        best_y     = 0
        # Only search upper half of 'before'; large shifts would fall outside
        search_end = h // 2
        for y in range(0, search_end - ref_h + 1, 2):
            diff = np.abs(ref - before[y:y + ref_h, :, :].astype(np.float32)).mean()
            if diff < best_diff:
                best_diff = diff
                best_y    = y

        # Require a confident match and a non-trivial shift
        if best_diff > 18.0 or best_y < 3:
            return None
        return best_y

    def measure_scroll_speed(self) -> Optional[float]:
        """
        Empirically measure scroll speed in px/sec:
          1. Capture the contact region.
          2. Scroll DOWN for TEST_SECS seconds.
          3. Capture again and measure the pixel shift.
          4. Scroll UP for TEST_SECS seconds to restore position.
        Returns px/sec, or None on failure.
        Stores the result in cfg.scroll_pixels_per_sec when successful.
        """
        if not HAS_PIL:
            self.log("Pillow (PIL) required for scroll speed measurement.")
            return None

        self._refresh_rect()
        r = self._abs_contact_region()
        if not r:
            self.log("Contact region not calibrated — complete Step 2 first.")
            return None
        if not self.cfg.contact_item_height:
            self.log("Row height not calibrated — complete Step 3 first.")
            return None

        ax, ay, aw, ah = r
        cx, cy = ax + aw // 2, ay + ah // 2
        TEST_SECS = 0.30

        self.log("Measuring scroll speed...")
        before = self._grab([ax, ay, aw, ah])
        if before is None:
            self.log("Screenshot failed.")
            return None

        self._bg_scroll(cx, cy, TEST_SECS, direction=-1)
        time.sleep(0.25)

        after = self._grab([ax, ay, aw, ah])

        # Immediately scroll back up to restore position
        self._bg_scroll(cx, cy, TEST_SECS + 0.05, direction=1)
        time.sleep(0.25)

        if after is None:
            self.log("Screenshot after scroll failed.")
            return None

        shift = self._find_scroll_shift(before, after)
        if not shift:
            self.log("Could not detect scroll shift — ensure the contact list "
                     "has more content below the visible area.")
            return None

        speed = shift / TEST_SECS
        self.log(f"Scroll speed measured: {shift}px in {TEST_SECS}s "
                 f"= {speed:.1f} px/sec")
        self.cfg.scroll_pixels_per_sec = speed
        return speed

    # ── Filter fingerprint (Emergency Stop) ───────────────────────────────────

    def _capture_filter_fingerprint(self) -> bool:
        """
        Snapshot the search/filter bar strip above the contact list.
        Called once at startup, before any automation begins.
        Any subsequent visual change in that area triggers Emergency Stop.
        """
        if not HAS_PIL or not self.cfg.contact_region or not self.zalo_rect:
            return False
        rx, ry, rw, _ = self.cfg.contact_region
        strip_h = 50
        abs_x = self.zalo_rect[0] + rx
        abs_y = self.zalo_rect[1] + ry - strip_h
        if abs_y < 0:
            abs_y = 0
        try:
            img = ImageGrab.grab(bbox=(abs_x, abs_y, abs_x + rw, abs_y + strip_h))
            self._filter_fingerprint = np.array(img)
            self.log(f"Filter fingerprint captured at screen ({abs_x},{abs_y}) "
                     f"size {rw}x{strip_h}px")
            return True
        except Exception as exc:
            self.log(f"Filter fingerprint capture failed: {exc}")
            return False

    def _check_filter_intact(self) -> bool:
        """
        Compare the current search-bar area to the startup fingerprint.
        Returns True (safe) or False (filter changed — emit Emergency Stop).
        Returns True when PIL is unavailable or fingerprint was never captured.
        """
        if not HAS_PIL or self._filter_fingerprint is None:
            return True
        if not self.cfg.contact_region or not self.zalo_rect:
            return True
        rx, ry, rw, _ = self.cfg.contact_region
        strip_h = self._filter_fingerprint.shape[0]
        abs_x = self.zalo_rect[0] + rx
        abs_y = self.zalo_rect[1] + ry - strip_h
        if abs_y < 0:
            abs_y = 0
        try:
            img     = ImageGrab.grab(bbox=(abs_x, abs_y, abs_x + rw, abs_y + strip_h))
            current = np.array(img)
            return self._similar(self._filter_fingerprint, current, threshold=0.85)
        except Exception:
            return True  # on capture error, don't halt

    # ── Element finders ───────────────────────────────────────────────────────

    def _find_info_btn(self) -> Optional[Tuple[int,int]]:
        """
        Locate the profile panel toggle button.
        Tries template matching first (most accurate), falls back to fixed offset.
        """
        region = self._zalo_region(0.28, 0.00, 1.00, 0.11)
        if os.path.exists(TPL_INFO) and region:
            pos = find_template(TPL_INFO, region, self.cfg.match_confidence)
            if pos:
                self.log(f"  Info button: template at {pos}")
                return pos

        if self.zalo_rect:
            zx, zy, zx2, zy2 = self.zalo_rect
            pos = (zx2 - 100, zy + 50)
            self.log(f"  Info button: position fallback at {pos}")
            return pos

        self.log("  Info button: not found (no window rect, no template)")
        return None

    def _find_and_activate_nickname_edit(self) -> Optional[str]:
        """
        Locate and click the pencil icon next to 'Ten goi nho'.

        Primary path (calibrated label position set):
          Starting from the calibrated label anchor, click at 5px steps rightward.
          After each click, Ctrl+C (no Ctrl+A) detects whether Zalo auto-selected
          the nickname text. Selected characters > 0 confirms edit mode activated.
          For empty-nickname contacts, a visual-delta + probe character is used.

        Fallback (no calibration): template matching then exhaustive grid scan.

        Returns the current nickname string ('' for empty) or None on failure.
        The returned value is used directly — no second Ctrl+A/Ctrl+C needed.
        """
        if not self.zalo_rect:
            self.log("  No Zalo rect")
            return None

        zx, zy, zx2, zy2 = self.zalo_rect
        zw, zh = zx2 - zx, zy2 - zy

        dlg_box = (zx + zw // 4, zy + zh // 4,
                   zx + 3 * zw // 4, zy + 3 * zh // 4)

        def _check_after_click(before_dlg) -> Optional[str]:
            # Measure visual change in the centre of the screen BEFORE touching
            # the clipboard, so any pending Ctrl+C below does not race with it.
            if HAS_PIL and before_dlg is not None:
                now_dlg = np.array(ImageGrab.grab(bbox=dlg_box))
                dlg_delta = int(
                    (np.abs(before_dlg.astype(int) - now_dlg.astype(int))
                     .max(axis=2) > 25).sum()
                )
                something_opened = dlg_delta > 5000
            else:
                dlg_delta = 0
                something_opened = False

            # Primary: Ctrl+C (no Ctrl+A) copies what Zalo auto-selected when
            # the pencil was clicked.  Selected characters > 0 = edit mode.
            pyperclip.copy(_SENTINEL)
            time.sleep(0.08)
            self._bg_hotkey(_VK_CONTROL, _VK_C)
            time.sleep(0.22)
            got = pyperclip.paste()
            if (got != _SENTINEL
                    and len(got) > 0
                    and "\n" not in got
                    and "\r" not in got
                    and len(got) < 250):
                self.log(f"    edit active — selected: {got!r}")
                return got

            # Empty-nickname contacts: the pencil click opens the rename field
            # but there is no existing text for Zalo to auto-select.
            # Detect via visual delta ONLY — absolutely no typewrite, Ctrl+A,
            # or Backspace here.  Those keys corrupt the contact-list
            # search/filter if focus has drifted to the search bar:
            #   Ctrl+A  → selects the entire filter query
            #   Backspace → deletes it, clearing the user's filter
            if something_opened:
                self.log(f"    edit active — empty nickname (visual delta={dlg_delta}px)")
                return ""

            return None

        def _scan_right(y: int, x_start: int, x_end: int, step: int = 5) -> Optional[str]:
            """Click from x_start to x_end at row y; screenshot dlg_box before each click."""
            for px in range(x_start, x_end + 1, step):
                before_dlg = np.array(ImageGrab.grab(bbox=dlg_box)) if HAS_PIL else None
                self._bg_click(px, y)
                time.sleep(0.50)
                result = _check_after_click(before_dlg)
                if result is not None:
                    self.log(f"  Pencil at ({px},{y})")
                    return result
            return None

        # ── Primary: calibrated label anchor ──────────────────────────────────
        # User picks the 'Ten goi nho' label position once in Calibration Step 4.
        # Scan rightward from that point — the pencil is just to its right.
        if self.cfg.nickname_label_rel:
            lx = zx + self.cfg.nickname_label_rel[0]
            ly = zy + self.cfg.nickname_label_rel[1]
            self.log(f"  Scanning from label ({lx},{ly})")
            result = _scan_right(ly, lx, zx2 - 5, step=5)
            if result is not None:
                return result
            self.log("  Pencil not found from calibrated position")
            return None

        # ── Fallback: template then exhaustive scan ────────────────────────────
        panel_region = self._zalo_region(0.63, 0.05, 1.00, 0.55)
        panel_cx     = zx2 - 160

        if os.path.exists(TPL_NICK_ICON):
            pos = find_template(TPL_NICK_ICON, panel_region, self.cfg.match_confidence)
            if pos:
                self.log(f"  Pencil icon template at {pos}")
                before_dlg = np.array(ImageGrab.grab(bbox=dlg_box)) if HAS_PIL else None
                self._bg_click(*pos);  time.sleep(0.50)
                result = _check_after_click(before_dlg)
                if result is not None:
                    return result

        if os.path.exists(TPL_NICK_LBL):
            pos = find_template(TPL_NICK_LBL, panel_region, self.cfg.match_confidence)
            if pos:
                lx, ly = pos
                self.log(f"  Nickname label template at ({lx},{ly}) — scanning right")
                result = _scan_right(ly, lx + 5, zx2 - 5, step=5)
                if result is not None:
                    return result

        if not HAS_PIL:
            self.log("  Pillow unavailable — set nickname label position in Calibration")
            return None

        # Exhaustive grid (y_rel 185-250 avoids avatar and Zalo-name pencil)
        self.log("  Exhaustive grid scan (y_rel 185-250)")
        for y_rel in range(185, 255, 8):
            result = _scan_right(zy + y_rel, panel_cx, zx2 - 5, step=6)
            if result is not None:
                return result

        self.log("  Could not find pencil — set nickname label position in Calibration")
        return None

    # ── Per-row rename ────────────────────────────────────────────────────────

    def _process_row(self, row_y: int, seq_num: int) -> Tuple[str, str, str]:
        prefix = self.cfg.prefix

        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                self._refresh_rect()

                # ── Step 1: Click contact row (background — no cursor movement) ─
                cx = self._contact_click_x()
                self.log(f"  [attempt {attempt}] bg-click ({cx}, {row_y})")
                self._bg_click(cx, row_y)
                time.sleep(self.cfg.action_delay)

                # ── Step 2: Find and activate nickname edit ────────────────────
                current = self._find_and_activate_nickname_edit()
                if current is None:
                    info = self._find_info_btn()
                    if info:
                        self.log("  Profile panel closed — opening it...")
                        self._bg_click(*info)
                        time.sleep(self.cfg.profile_delay)
                        current = self._find_and_activate_nickname_edit()

                if current is None:
                    self.log(f"  Could not activate nickname edit (attempt {attempt})")
                    self._bg_press(_VK_ESCAPE)
                    time.sleep(0.5)
                    continue

                self.log(f"  Current nickname: {current!r}")

                # ── Skip checks ───────────────────────────────────────────────
                if current and re.match(rf"^{re.escape(prefix)}\d+", current):
                    self._bg_press(_VK_ESCAPE)
                    self.log("  Skip (already prefixed)")
                    self._seen_names.add(current)
                    return ("skipped", current, current)

                if current and (current in self._seen_names
                                or self.tracker.is_processed(current)):
                    self._bg_press(_VK_ESCAPE)
                    self.log("  Skip (already processed)")
                    return ("skipped", current, current)

                # ── Build new name ─────────────────────────────────────────────
                new_name = (f"{prefix}{seq_num} {current}"
                            if current else f"{prefix}{seq_num}")

                # ── Dry-run ────────────────────────────────────────────────────
                if self.cfg.dry_run:
                    self._bg_press(_VK_ESCAPE)
                    self.log(f"  [DRY RUN] {current!r} -> {new_name!r}")
                    self.log_mgr.add_record(current, new_name, "Dry Run")
                    self._seen_names.add(current or str(row_y))
                    return ("renamed", current, new_name)

                # ── Focus-verify: confirm edit field is still active ───────────
                # For non-empty nicknames the field auto-selects on pencil click;
                # a Ctrl+C should return that text.  For empty nicknames we only
                # have the visual-delta signal from _find_and_activate, so we
                # do a lighter check: sentinel must NOT come back unchanged.
                if current:
                    pyperclip.copy(_SENTINEL)
                    time.sleep(0.05)
                    self._bg_hotkey(_VK_CONTROL, _VK_C)
                    time.sleep(0.18)
                    verify = pyperclip.paste()
                    if verify == _SENTINEL or len(verify) == 0:
                        self.log("  Rename field lost focus before write — aborting")
                        self._bg_press(_VK_ESCAPE)
                        time.sleep(0.5)
                        continue
                else:
                    # Empty nickname: verify the edit field is open by checking
                    # that a sentinel Ctrl+C clears (field is active and empty).
                    pyperclip.copy(_SENTINEL)
                    time.sleep(0.05)
                    self._bg_hotkey(_VK_CONTROL, _VK_C)
                    time.sleep(0.18)
                    verify = pyperclip.paste()
                    if verify != _SENTINEL and len(verify) > 0:
                        # Something unexpected is selected — field may have drifted
                        self.log(f"  Empty-nick verify: unexpected clipboard {verify!r} — aborting")
                        self._bg_press(_VK_ESCAPE)
                        time.sleep(0.5)
                        continue
                    # sentinel unchanged or empty — field is open with no text; OK

                # ── Write new name ─────────────────────────────────────────────
                # pyperclip.copy is set BEFORE _bg_select_paste so the clipboard
                # is ready when Ctrl+V fires.  Ctrl+A and Ctrl+V share ONE focus
                # operation so Chromium never clears the selection between them.
                self.log(f"  Writing {new_name!r}...")
                pyperclip.copy(new_name)
                self._bg_select_paste()             # Ctrl+A + Ctrl+V, one focus block
                time.sleep(0.22)

                # ── Pre-Enter verify: field must contain exactly new_name ───────
                # This is the gate for the Success log — we only trust the rename
                # succeeded if the field content matches what we intended to write.
                pyperclip.copy(_SENTINEL)
                time.sleep(0.05)
                self._bg_hotkey(_VK_CONTROL, _VK_C)
                time.sleep(0.20)
                field_check = pyperclip.paste()
                if field_check == _SENTINEL:
                    self.log("  Pre-Enter verify: field lost focus — retrying")
                    self._bg_press(_VK_ESCAPE);  time.sleep(0.5)
                    continue
                if field_check != new_name:
                    self.log(f"  Pre-Enter verify: got {field_check!r}, "
                             f"expected {new_name!r} — retrying")
                    self._bg_press(_VK_ESCAPE);  time.sleep(0.5)
                    continue

                self._bg_press(_VK_RETURN);         time.sleep(0.55)

                # ── Record — only reached when field verification passed ────────
                self.tracker.mark_processed(current, new_name, seq_num)
                self.log_mgr.add_record(current, new_name, "Success")
                self._seen_names.add(current or str(row_y))
                self.log(f"  {current!r} -> {new_name!r}")
                return ("renamed", current, new_name)

            except pyautogui.FailSafeException:
                self.log("FAILSAFE: mouse moved to corner — stopping.")
                self.stop()
                return ("failed", "", "")
            except Exception as exc:
                self.log(f"  Attempt {attempt} error: {exc}")
                time.sleep(1.0)

        self.log_mgr.add_record("?", "?", "Failed", f"row_y={row_y}")
        return ("failed", "", "")

    # ── Scroll ────────────────────────────────────────────────────────────────

    def _scroll_list(self):
        """
        Scroll the contact list.
        Smart mode: scrolls exactly one page (region_h / scroll_pixels_per_sec).
        Timed mode: scrolls for cfg.scroll_time seconds.
        Fallback: fixed notch scrolling when scroll_time == 0.
        """
        self._refresh_rect()
        r = self._abs_contact_region()
        if not r:
            self.log("  Scroll skipped — contact region not calibrated")
            return

        ax, ay, aw, ah = r
        cx, cy = ax + aw // 2, ay + ah // 2

        if (self.cfg.use_smart_scroll
                and self.cfg.scroll_pixels_per_sec > 0
                and self.cfg.contact_region):
            region_h   = self.cfg.contact_region[3]
            smart_time = region_h / self.cfg.scroll_pixels_per_sec
            self.log(f"  Smart scroll: {region_h}px / {self.cfg.scroll_pixels_per_sec:.1f}px/s"
                     f" = {smart_time:.2f}s")
            self._bg_scroll(cx, cy, smart_time)

        elif self.cfg.scroll_time > 0:
            self.log(f"  Scroll: {self.cfg.scroll_time:.2f}s")
            self._bg_scroll(cx, cy, self.cfg.scroll_time)

        else:
            notches = max(1, self.cfg.scroll_amount)
            dur = notches * 0.06
            self.log(f"  Fallback scroll: {notches} notches / {dur:.2f}s")
            self._bg_scroll(cx, cy, dur)

        time.sleep(self.cfg.scroll_delay)

    # ── Controls ──────────────────────────────────────────────────────────────

    def pause(self):
        self._pause.clear();  self.log("Paused.");  self.status("Paused")

    def resume(self):
        self._pause.set();  self.log("Resumed.");  self.status("Running")

    def stop(self):
        self._stop.set();  self._pause.set();  self.status("Stopped")

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def _wait_paused(self):
        self._pause.wait()

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self) -> bool:
        missing = []
        if not self.cfg.contact_region:      missing.append("Contact list region      (Step 2)")
        if not self.cfg.contact_item_height: missing.append("Contact row height       (Step 3)")
        if not self.cfg.nickname_label_rel:  missing.append("Nickname label position  (Step 4)")
        for path, label in [
            (TPL_INFO,      "Info-button template (Step 5, optional)"),
            (TPL_NICK_LBL,  "Nickname label template (Step 6a, optional)"),
            (TPL_NICK_ICON, "Nickname icon template  (Step 6b, optional)"),
        ]:
            if not os.path.exists(path):
                self.log(f"  Note: {label} not captured")
        if missing:
            self.log("Setup incomplete:")
            for m in missing:
                self.log(f"  - {m}")
            self.status("Not set up")
            return False
        return True

    # ── Main run loop ─────────────────────────────────────────────────────────

    def run(self):
        self._stop.clear();  self._seen_names.clear()
        self._cur_num = self.cfg.start_number

        self.status("Starting...")
        self.log("=" * 52)
        self.log("Automation started")
        if self.cfg.dry_run:         self.log("MODE: DRY RUN  (Zalo unchanged)")
        if self.cfg.background_mode: self.log("MODE: BACKGROUND  (focus restored between renames)")
        self.log("=" * 52)

        if not self._validate():    return
        if not self.find_zalo_window(): return

        self._bg_set_focus();  time.sleep(0.3)

        # Capture the search/filter bar fingerprint BEFORE any automation.
        # If the area changes mid-run, Emergency Stop fires immediately.
        if not self._capture_filter_fingerprint():
            self.log("Note: filter fingerprint unavailable — Emergency Stop "
                     "monitoring disabled (PIL required + contact region must be set)")

        prev_img = None;  no_change = 0;  total = 0;  scroll_n = 0
        consecutive_all_skipped = 0

        while not self.is_stopped():
            self._wait_paused()
            if self.is_stopped(): break

            self._bg_set_focus();  time.sleep(0.20)
            self._refresh_rect()

            # ── Emergency Stop: verify the search/filter bar is unchanged ────
            if not self._check_filter_intact():
                self.log("=" * 52)
                self.log("!!! EMERGENCY STOP !!!")
                self.log("The Zalo contact filter/search bar changed unexpectedly.")
                self.log("Automation halted — wrong contacts could be renamed.")
                self.log("Please restore your filter in Zalo before restarting.")
                self.log("=" * 52)
                self.status("EMERGENCY STOP — filter reset detected")
                self.stop()
                break

            curr_img = self._grab(self._abs_contact_region())

            # ── Fail-safe 1: post-scroll image identical → end of list ────────
            if curr_img is None:
                no_change = 0
            elif prev_img is not None and self._similar(prev_img, curr_img):
                no_change += 1
                self.log(f"Contact list unchanged after scroll ({no_change}/3)")
                if no_change >= 3:
                    self.log("=" * 52)
                    self.log("End of contact list — scroll had no effect 3 times.")
                    self.log(f"Session complete.  Total renamed: {total}")
                    self.log("=" * 52)
                    self.status("Completed — end of contact list")
                    self.stop()
                    break
            else:
                no_change = 0
            prev_img = curr_img

            rows = self._row_positions()
            if (self.cfg.use_smart_scroll
                    and self.cfg.contact_region
                    and self.cfg.contact_item_height):
                n = len(rows)
                self.log(f"--- cycle {scroll_n + 1}: smart batch {n} rows "
                         f"(region={self.cfg.contact_region[3]}px / "
                         f"item={self.cfg.contact_item_height}px) ---")
            else:
                n = self.cfg.contact_number
                self.log(f"--- cycle {scroll_n + 1}: processing {min(len(rows), n)} rows "
                         f"(contact_number={n}) ---")
            batch = rows[:n]

            # ── Fail-safe 2: no rows at all in the contact region ─────────────
            if not batch:
                self.log("=" * 52)
                self.log("No contact rows detected in the current view.")
                self.log("The list may be empty, or re-check calibration Steps 2 & 3.")
                self.log("=" * 52)
                self.status("Stopped — no contacts detected")
                self.stop()
                break

            batch_renamed = 0
            batch_skipped = 0
            batch_failed  = 0

            for row_y in batch:
                if self.is_stopped(): break
                self._wait_paused()

                result, _, _ = self._process_row(row_y, self._cur_num)
                if result == "renamed":
                    self._cur_num += 1;  total += 1;  batch_renamed += 1
                    self.progress(total)
                elif result == "skipped":
                    batch_skipped += 1
                elif result == "failed":
                    batch_failed += 1
                    if self.cfg.stop_on_error:
                        self.stop();  break

            # ── Fail-safe 3: entire batch was already-processed contacts ──────
            # Only trigger when every row was skipped and none failed
            # (failures are transient errors, not a signal that the list is done).
            if not self.is_stopped():
                if batch_renamed == 0 and batch_failed == 0 and batch_skipped > 0:
                    consecutive_all_skipped += 1
                    self.log(f"All {batch_skipped} contacts in this batch already "
                             f"processed ({consecutive_all_skipped}/3 consecutive batches)")
                    if consecutive_all_skipped >= 3:
                        self.log("=" * 52)
                        self.log("3 consecutive batches with all contacts already processed.")
                        self.log("No unprocessed contacts remain in the visible list.")
                        self.log(f"Session complete.  Total renamed: {total}")
                        self.log("=" * 52)
                        self.status("Completed — all contacts processed")
                        self.stop()
                        break
                else:
                    consecutive_all_skipped = 0

            if not self.is_stopped():
                self._scroll_list()
                scroll_n += 1

        self.log("=" * 52)
        self.log(f"Finished  --  renamed {total} contacts this session")
        self.log("=" * 52)
        self.status("Finished")

    # ── One-row test ──────────────────────────────────────────────────────────

    def test_one(self):
        self._stop.clear();  self._seen_names.clear()
        self._cur_num = self.cfg.start_number
        orig = self.cfg.dry_run;  self.cfg.dry_run = True
        self.log("=== TEST: 1 contact (dry run) ===")
        if self._validate() and self.find_zalo_window():
            self._bg_set_focus()
            rows = self._row_positions()
            if rows:
                self._process_row(rows[0], self._cur_num)
            else:
                self.log("No rows — check contact region & height.")
        self.cfg.dry_run = orig
        self.log("=== TEST done ===")
        self.status("Ready")

    # ── Click diagnostic ──────────────────────────────────────────────────────

    def debug_click_contact(self):
        """Focus Zalo and click the first contact row to verify coordinates."""
        self._stop.clear()
        self.log("=" * 52)
        self.log("CLICK DIAGNOSTIC  (no renaming)")
        self.log("=" * 52)

        if not self.find_zalo_window():
            self.status("Ready")
            return

        sw = pyautogui.size()
        self.log(f"Screen size: {sw.width}x{sw.height}")
        self.log(f"Zalo rect:   {self.zalo_rect}")

        render = self._find_render_hwnd()
        self.log(f"Render HWND: {render or 'not found (will use main HWND)'}")

        rows = self._row_positions()
        if not rows:
            self.log("Rows: NONE -- re-calibrate Steps 2 & 3.")
            self.status("Ready")
            return

        cx    = self._contact_click_x()
        row_y = rows[0]
        self.log(f"Region (rel): {self.cfg.contact_region}")
        self.log(f"Row height:   {self.cfg.contact_item_height}px  -> {len(rows)} rows")
        self.log(f"Click target: ({cx}, {row_y})  [contact #1]")
        self.log("Background-clicking now (no cursor movement) -- watch Zalo...")

        self._bg_click(cx, row_y)
        time.sleep(0.8)

        self.log("Did the first contact open in Zalo?")
        self.log("  YES -> background click working, calibration OK.")
        self.log("  NO  -> recalibrate Steps 2 & 3.")
        self.status("Ready")

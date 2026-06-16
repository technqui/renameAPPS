import json, os
from dataclasses import dataclass, field, asdict
from typing import Optional, List

CONFIG_FILE   = "zalo_renamer_config.json"
TEMPLATES_DIR = "templates"
TPL_INFO      = os.path.join(TEMPLATES_DIR, "info_btn.png")
TPL_NICK_LBL  = os.path.join(TEMPLATES_DIR, "nickname_label.png")
TPL_NICK_ICON = os.path.join(TEMPLATES_DIR, "nickname_icon.png")


@dataclass
class Config:
    prefix: str = "KH"
    start_number: int = 1
    contact_number: int = 10    # contacts to process per cycle = rows to scroll per cycle

    # seconds
    action_delay: float = 1.5
    profile_delay: float = 1.4
    scroll_delay: float  = 0.8
    scroll_amount: int   = 3
    scroll_speed: float  = 6.0   # notches per second during timed scroll (higher = faster)
    scroll_time: float   = 0.0   # seconds to scroll per cycle; 0 = use scroll_amount notches
    scroll_pixels_per_sec: float = 0.0
    use_smart_scroll: bool = False    # scroll exactly one page: region_h / px_per_sec
    max_retries: int     = 3

    dry_run: bool          = False
    background_mode: bool  = True   # restore prev window between renames
    stop_on_error: bool    = False

    log_file: str = "zalo_rename_log.csv"

    # Template-match confidence (0.0–1.0)
    match_confidence: float = 0.72

    # ── Contact list geometry (Zalo-window-relative) ──────────────────────────
    # All stored as pixel offsets from the Zalo window top-left (0, 0).
    # Re-computed from win32gui before every action, so window movement is fine.
    contact_region:      Optional[List[int]] = None   # [rx, ry, rw, rh]
    contact1_rel:        Optional[List[int]] = None   # center of 1st calibration contact
    contact2_rel:        Optional[List[int]] = None   # center of 2nd calibration contact
    contact_item_height: int = 0                      # |c2.y − c1.y|

    # ── Nickname label anchor (Zalo-window-relative) ───────────────────────────
    # Position of the 'Ten goi nho' label in the profile panel.
    # The pencil scan starts here and moves right in 5px steps.
    nickname_label_rel:  Optional[List[int]] = None   # [x, y]


def load_config() -> Config:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = Config()
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            return cfg
        except Exception:
            pass
    return Config()


def save_config(cfg: Config) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)

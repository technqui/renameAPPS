"""
Real rename test — finds the first contact WITHOUT the prefix and renames it.
"""
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, r"C:\Users\Admin\Downloads\renameAPPS")

from config_manager import load_config
from tracker import ContactTracker
from log_manager import LogManager
from automation import ZaloAutomation

def main():
    cfg = load_config()
    cfg.dry_run    = False   # REAL rename
    cfg.max_retries = 2

    print("Config:")
    print(f"  prefix={cfg.prefix!r}  start={cfg.start_number}")
    print(f"  contact_region={cfg.contact_region}")
    print(f"  contact_item_height={cfg.contact_item_height}")

    tracker = ContactTracker()
    log_mgr = LogManager()
    auto    = ZaloAutomation(cfg, tracker, log_mgr, log_cb=print)

    if not auto.find_zalo_window():
        return

    auto._focus_zalo()
    rows = auto._row_positions()
    print(f"\n{len(rows)} rows visible")

    import re
    prefix = cfg.prefix
    for i, row_y in enumerate(rows):
        print(f"\n─── row {i+1} (y={row_y}) ───")
        result, old, new = auto._process_row(row_y, cfg.start_number + i)
        print(f"Result: {result}  |  {old!r} → {new!r}")
        if result == "renamed":
            print("\n✓ Real rename succeeded — check Zalo to verify.")
            break
        if result == "failed":
            print("✗ Failed — stopping.")
            break
    else:
        print("\nAll visible rows already prefixed or skipped.")

if __name__ == "__main__":
    main()

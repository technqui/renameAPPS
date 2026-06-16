"""
Full workflow test (dry run) — 1 contact.
Tests: focus -> click contact -> open panel -> activate nickname edit -> read current -> skip write.
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
    cfg.dry_run = True    # dry run -- does NOT write to Zalo
    cfg.max_retries = 2

    print("Config loaded:")
    print(f"  contact_region    = {cfg.contact_region}")
    print(f"  contact_item_height = {cfg.contact_item_height}")
    print(f"  prefix = {cfg.prefix!r}, start = {cfg.start_number}")

    tracker = ContactTracker()
    log_mgr = LogManager()
    auto    = ZaloAutomation(cfg, tracker, log_mgr, log_cb=print)

    print("\nStarting test_one (dry run)...")
    auto.test_one()

if __name__ == "__main__":
    main()

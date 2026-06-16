"""
Single-contact rename test.
Runs one real rename (not dry-run) and prints every internal log line.
Usage:  python test_rename_one.py
        (Zalo must be open and visible before running)
"""
import time
from config_manager import load_config
from tracker import ContactTracker
from log_manager import LogManager
from automation import ZaloAutomation

log_lines = []

def on_log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    log_lines.append(line)
    print(line, flush=True)

def on_progress(n):
    print(f"  *** progress: {n} renamed ***", flush=True)

def on_status(s):
    print(f"  *** status: {s} ***", flush=True)

cfg     = load_config()
tracker = ContactTracker()
log_mgr = LogManager(cfg.log_file)

# Force single-contact run (not dry-run)
cfg.contact_number = 1
cfg.dry_run        = False

auto = ZaloAutomation(
    config      = cfg,
    tracker     = tracker,
    log_manager = log_mgr,
    log_cb      = on_log,
    progress_cb = on_progress,
    status_cb   = on_status,
)

print("=" * 60, flush=True)
print("Single-contact rename test", flush=True)
print(f"  prefix        : {cfg.prefix}", flush=True)
print(f"  start_number  : {cfg.start_number}", flush=True)
print(f"  smart_scroll  : {cfg.use_smart_scroll}", flush=True)
print(f"  contact_region: {cfg.contact_region}", flush=True)
print(f"  item_height   : {cfg.contact_item_height}px", flush=True)
print("=" * 60, flush=True)

for i in range(5, 0, -1):
    print(f"  Starting in {i}s  (switch to Zalo now)...", flush=True)
    time.sleep(1)

print("  GO", flush=True)
auto.run()

print(flush=True)
print("=" * 60, flush=True)
print("Log records this session:", flush=True)
for r in log_mgr.get_records():
    no = str(r.get("No", "")).strip()
    if no:
        print(
            f"  [{no:>4}] {str(r['Original Name']):<30} -> "
            f"{str(r['New Name']):<35} {r['Status']}  {r['Timestamp']}",
            flush=True,
        )
print("=" * 60, flush=True)

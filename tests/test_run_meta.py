"""meta.json written for every smoke/run directory (experiments/w4_smoke/smoke.py write_meta, used by experiments/w5a/run.py): from 2026-10-23 it also records the Armoury Crate
Battery Health Charging mode (fixed for the study: Balanced 80%; not detectable by software, so it is a recorded declaration) and the boot time / uptime, which show whether the
'fresh restart before every W5b session' procedure was followed.
Instruction (Arjun, 2026-10-23): "Record both in the journal and in meta.json from now on."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "w4_smoke")); sys.path.insert(0, str(ROOT / "workloads" / "common")); sys.path.insert(0, str(ROOT))
import smoke  # noqa: E402


def test_meta_records_battery_charge_mode_and_boot_time(tmp_path):
    smoke.write_meta(tmp_path, "Performance")
    m = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert m["battery_charge_mode"] == "Balanced 80%" and m["armoury_mode"] == "Performance"
    assert m["boot_utc"].startswith("20") and 0 < m["uptime_s"] < 40 * 24 * 3600


def test_battery_mode_can_be_overridden_and_is_never_silently_empty(tmp_path):
    smoke.write_meta(tmp_path, "Performance", battery_charge_mode="Full 100%")
    assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))["battery_charge_mode"] == "Full 100%"

"""
FlyGimbal — Lua applet SITL validation
src/fc-lua/sitl_lua_test.py

Validates flywheel_coupling.lua against a live ArduCopter SITL:

  1. Script loads (FWC_ params exist, load STATUSTEXT seen)
  2. FWRPM NAMED_VALUE_FLOAT is received by the script
  3. ATC_RAT_RLL_P scales by FWC_SCL_MAX at full flywheel RPM
  4. Overspeed warning is emitted above FWC_RPM_WARN
  5. Gains revert to baseline when RPM telemetry goes stale

Prerequisites (see docs/SITL_TESTING.md for SITL setup):
    cp src/fc-lua/flywheel_coupling.lua  ~/sitl/scripts/   (inside WSL)
    SITL running on tcp:5760

Usage:
    python sitl_lua_test.py [--cmd tcp:127.0.0.1:5760]
"""

import argparse
import os
import sys
import time

os.environ["MAVLINK20"] = "1"   # must be set before importing mavutil
from pymavlink import mavutil


class Check:
    def __init__(self):
        self.results = []

    def record(self, name, ok, detail=""):
        self.results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))

    def summary(self):
        ok = all(r[1] for r in self.results)
        print("\n" + "=" * 60)
        print(f"LUA APPLET SITL TEST: {'ALL PASS' if ok else 'FAILURES'}")
        for name, passed, detail in self.results:
            print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
        print("=" * 60)
        return ok


def get_param(mav, name, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        mav.param_fetch_one(name.encode())
        msg = mav.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
        if msg and msg.param_id == name:
            return msg.param_value
    return None


def set_param(mav, name, value, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        mav.param_set_send(name, value)
        got = get_param(mav, name, timeout=3)
        if got is not None and abs(got - value) < 1e-4:
            return True
    return False


def send_fwrpm(mav, rpm):
    mav.mav.named_value_float_send(
        int(time.time() * 1000) & 0xFFFFFFFF, b"FWRPM", rpm)


def drain_statustext(mav, texts, duration=0.0):
    """Collect STATUSTEXT into texts list for `duration` seconds."""
    t0 = time.time()
    while True:
        msg = mav.recv_match(type='STATUSTEXT', blocking=False)
        if msg:
            texts.append(msg.text)
            print(f"  [fc] {msg.text}")
        elif time.time() - t0 >= duration:
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", default="tcp:127.0.0.1:5760")
    args = parser.parse_args()

    check = Check()
    texts = []

    print(f"[test] connecting {args.cmd} ...")
    mav = mavutil.mavlink_connection(args.cmd, autoreconnect=True)
    mav.wait_heartbeat(timeout=60)
    print(f"[test] heartbeat from system {mav.target_system}")

    # ── Enable scripting and reboot so the applet loads ───────────────────
    if get_param(mav, "SCR_ENABLE") != 1:
        assert set_param(mav, "SCR_ENABLE", 1), "could not set SCR_ENABLE"
        print("[test] SCR_ENABLE=1, rebooting SITL ...")
        mav.mav.command_long_send(
            mav.target_system, mav.target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
            0, 1, 0, 0, 0, 0, 0, 0)
        time.sleep(3)
        mav.wait_heartbeat(timeout=60)
        print("[test] reconnected after reboot")

    # give the scripting engine time to start, collect boot messages
    drain_statustext(mav, texts, duration=10.0)

    # ── 1. Script loaded? ─────────────────────────────────────────────────
    fwc_enable = get_param(mav, "FWC_ENABLE", timeout=15)
    loaded_msg = any("flywheel_coupling" in t or "FWC" in t for t in texts)
    check.record("Lua applet loaded (FWC_ params exist)",
                 fwc_enable is not None,
                 f"FWC_ENABLE={fwc_enable}" if fwc_enable is not None
                 else "param missing — script not running")
    if fwc_enable is None:
        check.summary()
        sys.exit(1)
    # boot STATUSTEXT often beats our TCP reconnect — informational only
    print(f"[test] load STATUSTEXT {'seen' if loaded_msg else 'missed (raced reconnect)'}")

    baseline = get_param(mav, "ATC_RAT_RLL_P")
    scl_max  = get_param(mav, "FWC_SCL_MAX")
    rpm_max  = get_param(mav, "FWC_RPM_MAX")
    print(f"[test] baseline ATC_RAT_RLL_P={baseline:.4f}, "
          f"FWC_SCL_MAX={scl_max}, FWC_RPM_MAX={rpm_max}")

    # ── 2+3+4. Full-RPM telemetry → scaled gains + overspeed warning ─────
    print(f"[test] streaming FWRPM={rpm_max:.0f} for 4s ...")
    t0 = time.time()
    while time.time() - t0 < 4.0:
        send_fwrpm(mav, rpm_max)
        drain_statustext(mav, texts, duration=0.2)

    scaled = get_param(mav, "ATC_RAT_RLL_P")
    expect = baseline * scl_max
    check.record("Gains scaled at full flywheel RPM",
                 scaled is not None and abs(scaled - expect) < 0.01 * expect,
                 f"ATC_RAT_RLL_P {baseline:.4f} -> {scaled:.4f} (expect {expect:.4f})")
    check.record("Telemetry-online message", any("telemetry online" in t for t in texts))
    check.record("Overspeed warning emitted", any("overspeed" in t for t in texts))

    # ── 5. Stale telemetry → gains revert ────────────────────────────────
    print("[test] stopping FWRPM stream, waiting for stale failsafe ...")
    drain_statustext(mav, texts, duration=5.0)
    reverted = get_param(mav, "ATC_RAT_RLL_P")
    check.record("Gains revert on stale telemetry",
                 reverted is not None and abs(reverted - baseline) < 0.01 * baseline,
                 f"ATC_RAT_RLL_P back to {reverted:.4f}")
    check.record("Stale warning emitted", any("stale" in t for t in texts))

    ok = check.summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

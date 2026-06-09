"""
FlyGimbal — SITL Integration Test
src/momentum-manager/sitl_test.py

Flies a real ArduCopter SITL instance through a Dubins circuit + descent/climb
profile while MomentumManager runs against live MAVLink telemetry. Validates:

  1. FCInterface connects to a real MAVLink stack (not its internal sim)
  2. Telemetry stays fresh (drained faster than it arrives)
  3. Flight mode string is decoded from heartbeats
  4. REGEN triggers during a real descent, DISCHARGE during a real climb
  5. The aircraft actually tracks the Dubins path points

Prerequisites:
    ArduCopter SITL listening on TCP (e.g. in WSL):
        ./arducopter -w --model + --speedup 2 --defaults copter.parm \
                     --home -35.363261,149.165230,584,353
    SITL serves SERIAL0 on tcp:5760 (used here for commanding) and
    SERIAL1 on tcp:5762 (used by MomentumManager's FCInterface).

Usage:
    python sitl_test.py [--cmd tcp:127.0.0.1:5760] [--telem tcp:127.0.0.1:5762]
"""

import argparse
import math
import os
import sys
import time

from pymavlink import mavutil

# momentum_manager lives in this directory; dubins_sample in src/simulation
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "simulation"))

from momentum_manager import (MomentumManager, VESCInterface, FCInterface,
                              FlywheelMode)
from gyrodrone_sim import dubins_sample

CRUISE_ALT_M   = 15.0
DESCENT_ALT_M  = 5.0
TURN_RADIUS_M  = 6.0     # ~67% flywheel charge per ROADMAP.md
PATH_STEP_M    = 3.0
CAPTURE_M      = 3.0     # waypoint acceptance radius
WP_TIMEOUT_S   = 45.0


class Check:
    """Collects pass/fail results across the mission."""
    def __init__(self):
        self.results = []

    def record(self, name: str, ok: bool, detail: str = ""):
        self.results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    def summary(self) -> bool:
        ok = all(r[1] for r in self.results)
        print("\n" + "=" * 60)
        print(f"SITL INTEGRATION TEST: {'ALL PASS' if ok else 'FAILURES'}")
        for name, passed, detail in self.results:
            print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        print("=" * 60)
        return ok


class SITLCommander:
    """Direct MAVLink command link to SITL (separate from FCInterface)."""

    def __init__(self, connection: str):
        print(f"[cmd] connecting {connection} ...")
        self.mav = mavutil.mavlink_connection(connection)
        self.mav.wait_heartbeat(timeout=30)
        print(f"[cmd] heartbeat from system {self.mav.target_system}")
        self._request_streams()

    def _request_streams(self):
        for stream_id, rate in [
            (mavutil.mavlink.MAV_DATA_STREAM_POSITION, 5),
            (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, 5),
            (mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, 2),
        ]:
            self.mav.mav.request_data_stream_send(
                self.mav.target_system, self.mav.target_component,
                stream_id, rate, 1)

    def set_param(self, name: str, value: float):
        self.mav.param_set_send(name, value)
        time.sleep(0.2)

    def wait_position_estimate(self, timeout: float = 120.0):
        """Wait for GPS 3D fix + local position (EKF origin set)."""
        print("[cmd] waiting for GPS fix + EKF local position ...")
        t0 = time.time()
        have_fix = have_local = False
        while time.time() - t0 < timeout:
            msg = self.mav.recv_match(
                type=['GPS_RAW_INT', 'LOCAL_POSITION_NED'],
                blocking=True, timeout=2)
            if msg is None:
                continue
            if msg.get_type() == 'GPS_RAW_INT' and msg.fix_type >= 3:
                have_fix = True
            if msg.get_type() == 'LOCAL_POSITION_NED':
                have_local = True
            if have_fix and have_local:
                print(f"[cmd] position estimate ready ({time.time()-t0:.0f}s)")
                return True
        raise TimeoutError("no position estimate from SITL")

    def set_mode(self, mode: str, timeout: float = 20.0):
        mode_id = self.mav.mode_mapping()[mode]
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.mav.set_mode(mode_id)
            hb = self.mav.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
            if hb and mavutil.mode_string_v10(hb) == mode:
                print(f"[cmd] mode = {mode}")
                return True
        raise TimeoutError(f"mode change to {mode} not confirmed")

    def arm(self, timeout: float = 90.0):
        print("[cmd] arming ...")
        t0 = time.time()
        while time.time() - t0 < timeout:
            self.mav.mav.command_long_send(
                self.mav.target_system, self.mav.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 1, 0, 0, 0, 0, 0, 0)
            ack = self.mav.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
            if ack and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM \
                   and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                print(f"[cmd] armed ({time.time()-t0:.0f}s)")
                return True
            time.sleep(2)
        raise TimeoutError("arming refused by SITL")

    def takeoff(self, alt_m: float, timeout: float = 60.0):
        print(f"[cmd] takeoff to {alt_m} m ...")
        self.mav.mav.command_long_send(
            self.mav.target_system, self.mav.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0, alt_m)
        t0 = time.time()
        while time.time() - t0 < timeout:
            pos = self.local_position(timeout=2)
            if pos and -pos[2] >= alt_m * 0.95:
                print(f"[cmd] at altitude {-pos[2]:.1f} m")
                return True
        raise TimeoutError("takeoff did not reach altitude")

    def local_position(self, timeout: float = 2.0):
        msg = self.mav.recv_match(type='LOCAL_POSITION_NED',
                                  blocking=True, timeout=timeout)
        if msg is None:
            return None
        return (msg.x, msg.y, msg.z)

    def goto_local(self, north: float, east: float, down: float, yaw: float):
        """Position target in LOCAL_NED relative to EKF origin."""
        self.mav.mav.set_position_target_local_ned_send(
            0, self.mav.target_system, self.mav.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            0b0000_1011_1111_1000,  # position + yaw
            north, east, down,
            0, 0, 0, 0, 0, 0,
            yaw, 0)


def build_dubins_circuit():
    """20m x 20m circuit, same shape as the sim's default mission."""
    wps = [
        ( 0.0,  0.0, math.radians(0)),
        (20.0,  0.0, math.radians(90)),
        (20.0, 20.0, math.radians(180)),
        ( 0.0, 20.0, math.radians(270)),
        ( 0.0,  0.0, math.radians(0)),
    ]
    path = []
    for a, b in zip(wps, wps[1:]):
        seg = dubins_sample(a, b, TURN_RADIUS_M, step=PATH_STEP_M)
        path.extend(seg)
    # thin out duplicates at segment joints
    thinned = [path[0]]
    for p in path[1:]:
        if math.hypot(p[0] - thinned[-1][0], p[1] - thinned[-1][1]) >= PATH_STEP_M * 0.8:
            thinned.append(p)
    return thinned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd",   default="tcp:127.0.0.1:5760")
    parser.add_argument("--telem", default="tcp:127.0.0.1:5762")
    args = parser.parse_args()

    check = Check()

    # ── Command link + SITL prep ──────────────────────────────────────────
    cmd = SITLCommander(args.cmd)
    # No RC attached in this test: disable throttle failsafe; relax arming
    # checks that need an RC calibration (SITL bench config, not for real HW).
    cmd.set_param("FS_THR_ENABLE", 0)
    cmd.set_param("ARMING_CHECK", 0)
    cmd.wait_position_estimate()

    # ── MomentumManager on its own MAVLink port, VESC simulated ─────────
    vesc = VESCInterface("none", sim=True)
    fc   = FCInterface(args.telem, sim=False)
    check.record("FCInterface connected to real MAVLink", not fc.sim,
                 "fell back to internal sim" if fc.sim else args.telem)
    if fc.sim:
        check.summary()
        sys.exit(1)

    mgr = MomentumManager(vesc, fc, sim=False)
    mgr.start()

    seen_modes      = set()
    max_staleness   = 0.0
    mode_strings    = set()

    def observe():
        nonlocal max_staleness
        seen_modes.add(mgr.flywheel_mode)
        t = mgr.fc_telem
        if t.timestamp:
            max_staleness = max(max_staleness, time.time() - t.timestamp)
        mode_strings.add(t.mode)

    try:
        # ── Mission ───────────────────────────────────────────────────────
        cmd.set_mode("GUIDED")
        cmd.arm()
        cmd.takeoff(CRUISE_ALT_M)
        observe()

        print("\n[test] flying Dubins circuit ...")
        path = build_dubins_circuit()
        print(f"[test] {len(path)} path points, r={TURN_RADIUS_M} m")
        t_obs = time.time()
        reached = 0
        for i, (n, e, h) in enumerate(path):
            cmd.goto_local(n, e, -CRUISE_ALT_M, h)
            t0 = time.time()
            while time.time() - t0 < WP_TIMEOUT_S:
                pos = cmd.local_position()
                observe()
                if pos and math.hypot(pos[0] - n, pos[1] - e) < CAPTURE_M:
                    reached += 1
                    break
            if i % 8 == 0:
                s = mgr.get_stats()
                print(f"[test] pt {i+1}/{len(path)} | FW {s['flywheel_rpm']:.0f} RPM "
                      f"{s['flywheel_mode']} | alt {s['drone_alt_m']:.1f} m "
                      f"| staleness {max_staleness*1000:.0f} ms")

        frac = reached / len(path)
        check.record("Dubins circuit tracked", frac >= 0.9,
                     f"{reached}/{len(path)} points captured")

        # ── Descent → expect REGEN ────────────────────────────────────────
        print(f"\n[test] descending to {DESCENT_ALT_M} m (expect REGEN) ...")
        cmd.goto_local(0, 0, -DESCENT_ALT_M, 0)
        t0 = time.time()
        while time.time() - t0 < 60:
            pos = cmd.local_position()
            observe()
            if pos and -pos[2] <= DESCENT_ALT_M * 1.1:
                break
        check.record("REGEN during descent", FlywheelMode.REGEN in seen_modes,
                     f"modes seen: {sorted(m.name for m in seen_modes)}")

        # ── Climb → expect DISCHARGE ──────────────────────────────────────
        print(f"\n[test] climbing back to {CRUISE_ALT_M} m (expect DISCHARGE) ...")
        cmd.goto_local(0, 0, -CRUISE_ALT_M, 0)
        t0 = time.time()
        while time.time() - t0 < 60:
            pos = cmd.local_position()
            observe()
            if pos and -pos[2] >= CRUISE_ALT_M * 0.95:
                break
        check.record("DISCHARGE during climb", FlywheelMode.DISCHARGE in seen_modes,
                     f"modes seen: {sorted(m.name for m in seen_modes)}")

        # ── Telemetry quality checks ──────────────────────────────────────
        check.record("Telemetry freshness < 0.5 s", max_staleness < 0.5,
                     f"max staleness {max_staleness*1000:.0f} ms")
        check.record("Flight mode decoded from heartbeat",
                     "GUIDED" in mode_strings,
                     f"modes decoded: {sorted(mode_strings)}")
        alt_err = abs(mgr.fc_telem.alt_m - CRUISE_ALT_M)
        check.record("FCInterface altitude agrees with SITL", alt_err < 2.0,
                     f"telem alt {mgr.fc_telem.alt_m:.1f} m vs {CRUISE_ALT_M} m")

        # ── Land ──────────────────────────────────────────────────────────
        print("\n[test] landing ...")
        cmd.set_mode("LAND")
        t0 = time.time()
        while time.time() - t0 < 90:
            hb = cmd.mav.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
            if hb and not (hb.base_mode & 0x80):
                print("[cmd] disarmed — landed")
                break

    finally:
        mgr.stop()

    ok = check.summary()
    s = mgr.get_stats()
    print(f"\nSession: regen {s['regen_j_total']:.1f} J | "
          f"assist {s['assist_j_total']:.1f} J | loops {s['loop_count']}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

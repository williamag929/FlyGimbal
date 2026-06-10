"""
Quick SITL flight demo — arm, takeoff, hover, land.
Connects to SERIAL1 (5762) so Mission Planner on 5760 stays alive.

Usage: python sitl_fly_demo.py [alt_m] [hover_s]
  alt_m   target altitude in metres  (default 5)
  hover_s seconds to hover           (default 5)
"""
import sys
import time
from pymavlink import mavutil

PORT = "tcp:127.0.0.1:5762"
TARGET_ALT_M = int(sys.argv[1]) if len(sys.argv) > 1 else 5
HOVER_S      = int(sys.argv[2]) if len(sys.argv) > 2 else 5

def wait_msg(mav, msg_type, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type=msg_type, blocking=True, timeout=1)
        if msg:
            return msg
    return None

def set_mode(mav, mode_name):
    mode_id = mav.mode_mapping()[mode_name]
    mav.mav.set_mode_send(
        mav.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    # Wait for FC heartbeat confirming mode — skip GCS heartbeats (Mission Planner)
    for _ in range(10):
        hb = mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and hb.get_srcSystem() == mav.target_system:
            if mavutil.mode_string_v10(hb) == mode_name:
                return True
    return False

def arm(mav):
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0,
    )
    ack = wait_msg(mav, "COMMAND_ACK", timeout=5)
    return ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED

def takeoff(mav, alt_m):
    mav.mav.command_long_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, alt_m,
    )
    ack = wait_msg(mav, "COMMAND_ACK", timeout=5)
    return ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED

def current_alt(mav):
    # Drain queue and return the freshest GLOBAL_POSITION_INT
    latest = None
    while True:
        msg = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=False)
        if msg is None:
            break
        latest = msg
    if latest is None:
        # Nothing in queue — do one blocking wait
        latest = mav.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
    return (latest.relative_alt / 1000.0) if latest else 0.0

def land(mav):
    set_mode(mav, "LAND")

def main():
    print(f"Connecting to SITL on {PORT} ...")
    mav = mavutil.mavlink_connection(PORT)

    print("Waiting for heartbeat ...")
    mav.wait_heartbeat()
    print(f"  Connected — system {mav.target_system}, component {mav.target_component}")

    # Drain stale messages
    for _ in range(20):
        mav.recv_match(blocking=False)

    # SERIAL1 (5762) doesn't auto-stream — request all telemetry at 4 Hz
    mav.mav.request_data_stream_send(
        mav.target_system, mav.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1,
    )
    time.sleep(0.5)

    print("Setting GUIDED mode ...")
    ok = set_mode(mav, "GUIDED")
    print(f"  GUIDED: {'OK' if ok else 'may already be set, continuing'}")

    print("Arming ...")
    ok = arm(mav)
    print(f"  Arm: {'OK' if ok else 'FAILED — check pre-arm errors in Mission Planner'}")
    if not ok:
        return

    time.sleep(1)

    print(f"Takeoff to {TARGET_ALT_M} m ...")
    takeoff(mav, TARGET_ALT_M)

    climb_budget = max(30, TARGET_ALT_M * 2)   # ~2s per metre at sim speed
    print("  Climbing", end="", flush=True)
    for _ in range(climb_budget):
        alt = current_alt(mav)
        print(f"\r  Climbing ... {alt:.1f} m / {TARGET_ALT_M} m   ", end="", flush=True)
        if alt >= TARGET_ALT_M * 0.90:
            break
        time.sleep(1)
    print(f"\r  Reached {current_alt(mav):.1f} m                  ")

    print(f"Hovering {HOVER_S} seconds — watch Mission Planner ...")
    for i in range(HOVER_S, 0, -1):
        alt = current_alt(mav)
        print(f"  {i}s  alt={alt:.1f} m")
        time.sleep(1)

    print("Landing ...")
    land(mav)

    descend_budget = max(30, TARGET_ALT_M * 2)
    print("  Descending", end="", flush=True)
    for _ in range(descend_budget):
        alt = current_alt(mav)
        print(f"\r  Descending ... {alt:.1f} m   ", end="", flush=True)
        if alt < 0.3:
            break
        time.sleep(1)
    print(f"\r  Landed at {current_alt(mav):.1f} m              ")

    print("Done. Drone is on the ground.")

if __name__ == "__main__":
    main()

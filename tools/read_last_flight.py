"""
Parse the last flight from ArduPilot DataFlash log and print a summary.
Covers: mode changes, arm/disarm, altitude profile, attitude extremes.
"""
import sys
from pymavlink import mavutil
from pymavlink.DFReader import DFReader_binary

LOG_PATH = "/root/sitl-patched/logs/00000001.BIN"

def wsl_path(p):
    # convert WSL path for use via wsl -e
    return p

def main():
    import subprocess, os, tempfile, shutil

    # Copy log from WSL to a Windows temp path
    tmp = tempfile.mktemp(suffix=".bin")
    print("Copying log from WSL ...")
    r = subprocess.run(
        ["wsl", "-e", "bash", "-c", f"cat {LOG_PATH}"],
        stdout=open(tmp, "wb"), stderr=subprocess.PIPE
    )
    if r.returncode != 0:
        print("Failed to read log:", r.stderr.decode())
        sys.exit(1)
    size_mb = os.path.getsize(tmp) / 1e6
    print(f"  {size_mb:.1f} MB — scanning for last flight ...")

    mlog = DFReader_binary(tmp)

    # Collect all flights (ARM → DISARM boundaries)
    flights = []
    current = None

    while True:
        msg = mlog.recv_msg()
        if msg is None:
            break
        t = msg.get_type()

        if t == "EV":
            # EV Id=10 = ARM, Id=11 = DISARM
            if msg.Id == 10:
                current = {"arm_t": msg._timestamp, "msgs": [], "modes": [], "alt": [], "roll": [], "pitch": []}
            elif msg.Id == 11 and current:
                current["disarm_t"] = msg._timestamp
                flights.append(current)
                current = None

        if current is None:
            continue

        if t == "MODE":
            current["modes"].append((msg._timestamp - current["arm_t"], msg.Mode, getattr(msg, "ModeNum", "?")))
        elif t == "CTUN":
            current["alt"].append((msg._timestamp - current["arm_t"], msg.Alt, msg.DAlt))
        elif t == "ATT":
            current["roll"].append(msg.Roll)
            current["pitch"].append(msg.Pitch)

    mlog.close()
    try:
        os.unlink(tmp)
    except Exception:
        pass

    if not flights:
        print("No complete ARM→DISARM flights found in log.")
        return

    print(f"\nTotal flights in log: {len(flights)}")
    f = flights[-1]
    duration = f.get("disarm_t", f["arm_t"]) - f["arm_t"]
    print(f"\n=== Last flight ===")
    print(f"  Duration : {duration:.1f} s")

    if f["modes"]:
        print(f"  Modes    :")
        for dt, mode, num in f["modes"]:
            print(f"    +{dt:5.1f}s  {mode} ({num})")

    if f["alt"]:
        alts = [a for _, a, _ in f["alt"]]
        dalts = [d for _, _, d in f["alt"]]
        print(f"  Altitude : max={max(alts):.1f} m  min={min(alts):.1f} m  target_at_peak={dalts[alts.index(max(alts))]:.1f} m")
        # Print altitude profile in 5-second buckets
        print(f"  Profile  :")
        bucket = 5
        last_b = -1
        for dt, alt, dalt in f["alt"]:
            b = int(dt / bucket) * bucket
            if b != last_b:
                print(f"    +{b:4d}s  {alt:5.1f} m (target {dalt:.1f} m)")
                last_b = b

    if f["roll"]:
        print(f"  Roll     : max={max(f['roll']):.1f}°  min={min(f['roll']):.1f}°")
        print(f"  Pitch    : max={max(f['pitch']):.1f}°  min={min(f['pitch']):.1f}°")

if __name__ == "__main__":
    main()

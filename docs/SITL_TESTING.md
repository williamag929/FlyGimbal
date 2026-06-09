# SITL Integration Testing — Momentum Manager

Validates `src/momentum-manager/momentum_manager.py` against a **real ArduCopter
SITL** (Software In The Loop) instance before any hardware exists. The test
flies a full mission — takeoff, Dubins circuit, descent (REGEN), climb
(DISCHARGE), land — while the MomentumManager consumes live MAVLink telemetry.

## What it validates

| Check | Why it matters |
|---|---|
| FCInterface connects to real MAVLink | Catches connection-string / heartbeat bugs the internal sim hides |
| Dubins circuit tracked (33 points) | Guided-mode position targets work end-to-end |
| REGEN triggers on real descent | The vz sign convention and state machine survive a real EKF |
| DISCHARGE triggers on real climb | Same, ascending branch |
| Telemetry staleness < 0.5 s | Verifies the message-drain loop keeps up with stream rates |
| Mode decoded from heartbeat | `telem.mode` reads `"GUIDED"`, not `"UNKNOWN"` |
| Altitude agreement | GLOBAL_POSITION_INT scaling is correct |

Last full run (2026-06-09): **7/7 PASS**, max telemetry staleness 96 ms,
33/33 path points captured.

## Setup (Windows + WSL2)

The prebuilt SITL binary runs in WSL; the test runs on Windows and connects
over localhost (WSL2 forwards the ports automatically).

```bash
# Inside WSL (one-time)
mkdir -p ~/sitl && cd ~/sitl
curl -sL -o arducopter https://firmware.ardupilot.org/Copter/stable/SITL_x86_64_linux_gnu/arducopter
curl -sL -o copter.parm https://raw.githubusercontent.com/ArduPilot/ardupilot/master/Tools/autotest/default_params/copter.parm
chmod +x arducopter
```

## Running the test

**Terminal 1 — SITL (keep this window open):**

```bash
wsl -e bash -c "cd ~/sitl && rm -f eeprom.bin && exec ./arducopter -w --model + --speedup 2 --defaults copter.parm --home -35.363261,149.165230,584,353"
```

**Terminal 2 — test (Windows):**

```powershell
.venv\Scripts\pip install pymavlink        # one-time
.venv\Scripts\python src\momentum-manager\sitl_test.py
```

Takes ~3 minutes. Exits 0 on all-pass, 1 on any failure.

## Gotchas (learned the hard way)

1. **Don't detach SITL inside WSL** (`nohup`/`setsid` + closing the session).
   WSL2 tears down the VM when the launching `wsl.exe` exits, killing SITL
   silently. Keep a foreground `wsl.exe` alive for the duration.
2. **Don't port-probe 5760.** SITL's SERIAL0 exits when its first TCP client
   disconnects. The test itself must be the first connection.
3. **Two MAVLink clients need two ports.** The test commands on `tcp:5760`
   (SERIAL0); the MomentumManager's FCInterface listens on `tcp:5762`
   (SERIAL1). SERIAL1 only binds after SERIAL0 has a client.
4. The test sets `ARMING_CHECK=0` and `FS_THR_ENABLE=0` because no RC is
   attached. **Bench config only — never on real hardware.**

## Known sim-vs-real gaps this does NOT cover

- The VESC side is still simulated (`VESCInterface(sim=True)`) — regen/assist
  joule numbers are bookkeeping estimates, not physics.
- ArduCopter has **no gyroscopic feed-forward** for the flywheel; that
  integration question (Lua script vs. firmware patch) is still open and must
  be resolved before Phase 2 flight with the flywheel spinning.

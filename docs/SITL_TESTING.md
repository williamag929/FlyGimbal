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

## Lua applet test — flywheel coupling mitigation

`src/fc-lua/flywheel_coupling.lua` runs **on the flight controller**. On stock
firmware it provides gain-scheduling mitigation; on patched firmware (see
below) it additionally drives true rate-loop feed-forward. The applet:

- receives flywheel RPM from the companion (`NAMED_VALUE_FLOAT "FWRPM"`,
  broadcast at 5 Hz by `momentum_manager.py`)
- gain-schedules `ATC_RAT_RLL/PIT` P+D up to `FWC_SCL_MAX` (default 1.25×)
  at full RPM — runtime-only writes, no flash wear
- warns the GCS on overspeed, reverts gains if RPM telemetry goes stale

Validate it against SITL (script must be in `~/sitl/scripts/` before launch):

```powershell
wsl -e bash -lc "mkdir -p ~/sitl/scripts && cp /mnt/d/Projects/Python/FlyGimbal/src/fc-lua/flywheel_coupling.lua ~/sitl/scripts/"
# start SITL (terminal 1, as above), then:
.venv\Scripts\python src\fc-lua\sitl_lua_test.py
```

Last run (2026-06-09): **6/6 PASS** — gains scaled 0.135→0.169 at 20k RPM,
overspeed + stale-failsafe messages confirmed.

Implementation note: `mavlink:receive_chan()` delivers a serialized
`mavlink_message_t` struct (checksum@1, magic@3, msgid u24@10, payload@13),
NOT raw wire bytes. Parsing it as wire format fails silently.

## Patched firmware test — true gyroscopic feed-forward

The `tau_roll += H*q; tau_pitch -= H*p` term validated in `gyrodrone_sim.py`
is now available as a real firmware patch — see
[src/firmware-patch/README.md](../src/firmware-patch/README.md). The Lua applet
auto-detects it: on patched builds it announces
`FWC: firmware feed-forward active` and pushes live `H = I·ω` into the rate
loop; on stock builds it announces `FWC: stock firmware, gain scheduling only`
and falls back gracefully.

Build + validate (WSL):

```bash
bash /mnt/d/Projects/Python/FlyGimbal/src/firmware-patch/build_sitl.sh
# launch ~/sitl-patched/arducopter (same launch command, cd ~/sitl-patched), then:
# .venv\Scripts\python src\fc-lua\sitl_lua_test.py        (from Windows)
```

Last run (2026-06-09, ArduPilot master @ 1b7d3cde): **7/7 PASS** — including
`FWC: firmware feed-forward active`, and the stale-telemetry failsafe zeroing
the feed-forward (`set_flywheel_momentum(0)`) alongside the gain revert.

To verify the stock-firmware fallback path instead, run the same test against
the unpatched binary with `--stock`.

## Known sim-vs-real gaps this does NOT cover

- The VESC side is still simulated (`VESCInterface(sim=True)`) — regen/assist
  joule numbers are bookkeeping estimates, not physics.
- `FWC_ACT_NM` (actuator output per N·m) is a placeholder (0.8) until measured
  on the real airframe — SITL confirms the plumbing, not the scaling.

# Flywheel Feed-Forward Firmware Patch

True gyroscopic feed-forward for the FlyGimbal flywheel. The sim-validated
compensation (`tau_roll += H*q`, `tau_pitch -= H*p`) cannot be done from Lua —
scripting has no torque injection into the rate loop — so this small patch adds
it to ArduPilot itself.

**Architecture:** firmware computes the fast term (`H × gyro`) at 400 Hz inside
`rate_controller_run_dt()`; the Lua applet ([flywheel_coupling.lua](../fc-lua/flywheel_coupling.lua))
refreshes the slowly-varying angular momentum `H = I·ω` at ~10 Hz via a new
scripting binding. If the refresh stops for 3 s, the feed-forward zeroes itself.

## What it changes (4 anchored edits, ~30 lines)

| File | Change |
|---|---|
| `AC_AttitudeControl.h` | `set_flywheel_momentum(h_z_nms, act_per_nm)` inline setter |
| `AC_AttitudeControl.h` | 3 state members: `_flywheel_h_z`, `_flywheel_act_per_nm`, `_flywheel_update_ms` |
| `AC_AttitudeControl_Multi.cpp` | `fw_ff_roll/pitch` terms added to `set_roll`/`set_pitch` in the rate loop, 3 s staleness cutoff |
| `bindings.desc` | Lua binding: `AC_AttitudeControl:set_flywheel_momentum(h, act_per_nm)` |

Sign convention (verified against simulation): flywheel spin axis is body Z;
coupling torque on the airframe is `(-H·q, +H·p)`, the feed-forward adds the
negative. At 20,000 RPM with the as-built v01 rotor (I = 1.24e-4 kg·m²),
H ≈ 0.26 N·m·s.

## Files

- `apply_patch.py` — anchored patch applier. Idempotent; fails loudly if
  upstream anchors moved. Preferred way to apply (survives upstream drift
  better than a line-number diff).
- `flywheel_ff.patch` — exported `git diff`, exact record of the validated
  change. Applies cleanly to ArduPilot master @ `1b7d3cde` (2026-06-09).
- `build_sitl.sh` — one command: apply patch → export diff → waf configure →
  waf copter → stage binary + Lua + params to `~/sitl-patched/`.

## Build (WSL)

```bash
git clone --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/ArduPilot/ardupilot.git ~/ardupilot
pip3 install --break-system-packages empy==3.3.4 pexpect future

bash /mnt/d/Projects/Python/FlyGimbal/src/firmware-patch/build_sitl.sh
```

## Validation (2026-06-09)

Patched SITL + `src/fc-lua/sitl_lua_test.py`: **7/7 PASS**, including
`FWC: firmware feed-forward active` — the binding exists and the Lua applet
pushes live momentum into the rate loop. Stale-telemetry failsafe reverts
gains and zeroes the feed-forward. See [docs/SITL_TESTING.md](../../docs/SITL_TESTING.md).

## Real-hardware tuning

`FWC_ACT_NM` (normalized actuator output per N·m) must be estimated for the
real airframe — start at 0.8 (≈ 1/τ_max) and tune from logs comparing
commanded vs achieved rates during flywheel spin-up. Until tuned, keep
`FWC_ENABLE=2` (gain scheduling) as the safety net; it runs alongside the
feed-forward.

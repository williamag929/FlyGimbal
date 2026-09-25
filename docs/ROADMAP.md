# Development Roadmap — FlyGimbal

_Last updated: 2026-09-24._ Week numbers count from the Phase 1 parts order,
which has not been placed yet. See [STRUCTURE.md](STRUCTURE.md) for where each
file lives.

## Where We Are

| Area | State |
|---|---|
| Simulation | Complete, with wind, gust and sensor-noise robustness |
| Software vs ArduCopter SITL | Complete: momentum manager, Lua script, firmware patch, flight demo |
| CAD | v02 generated. Fillets and the flywheel boss flange update are pending |
| Hardware | Not started. Next step is ordering plates, rotor and containment cup |
| Automated tests | Pytest suite and CI in place (2026-09-24) |

---

## Phase 0 — Architecture (Complete)
- [x] Physics validation (gyroscopic effect, FESS math, Dubins path)
- [x] Component selection and BOM
- [x] CAD specifications drafted
- [x] GitHub documentation structure

---

## Phase 0.5 — Physics Simulation (Complete)

**Goal:** Validate full system dynamics before committing to hardware build.

- [x] 6-DOF rigid-body dynamics (NED frame, ZYX Euler, Euler integration)
- [x] Flywheel FESS model (RPM integration, bearing friction, regenerative braking)
- [x] Thrust-vectoring gimbal model (Savox SH-0257MG rate-limited servos)
- [x] Momentum-aware Dubins path planner (inline, no external dependency)
- [x] Cascade controller: position → accel → tilt + wrench allocation
- [x] Gyroscopic feed-forward (cancels flywheel coupling on pitch/roll)
- [x] 8-panel telemetry dashboard (trajectory, energy, gimbals, attitude, speed)

### Simulation Results — Circuit Mission (20m × 20m, 5 waypoints)

| Metric | Value |
|---|---|
| Mission duration | ~20 seconds |
| Cruise speed | 5.0 m/s (achieved) |
| Altitude tracking error | ±0.5 m |
| Flywheel RPM (nominal) | 15,000 RPM (67% charge) |
| Regen energy recovered | ~16 J per circuit (as-built rotor I=1.24e-4) |
| Turning radius (67% FW charge) | 5.9 m (vs 8.8 m empty) |
| Max roll during arc turns | < 1° (gyroscopic stabilization active) |

### Run the Simulation

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# Default circuit (5 waypoints, 20 m x 20 m)
.venv/Scripts/python src/simulation/gyrodrone_sim.py

# Other profiles: circuit | square | figure8 | lawnmower
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission figure8
.venv/Scripts/python src/simulation/gyrodrone_sim.py --no-regen   # FESS disabled comparison
.venv/Scripts/python src/simulation/gyrodrone_sim.py --dt 0.005   # high-fidelity

# Robustness: steady wind (m/s), wind direction (deg), gust sigma, sensor noise
.venv/Scripts/python src/simulation/gyrodrone_sim.py --wind 8 --wind-dir 90 --gust 3 --noise --seed 42

# Other options
.venv/Scripts/python src/simulation/gyrodrone_sim.py --speed 6 --altitude 15
.venv/Scripts/python src/simulation/gyrodrone_sim.py --no-plot    # console only, no PNG

# Automated checks (sampler, planner, circuit, windy circuit)
.venv/Scripts/python -m pytest tests/ -v
```

### Key Findings

1. **Gyroscopic feed-forward is mandatory.** Without canceling flywheel angular momentum coupling, pitch maneuvers induce ~10° spurious roll. The `tau_r += L_fw*q` term in the controller eliminates this.
2. **Wrench allocation decouples throttle from attitude.** Mapping desired torques (Nm) directly to motor speeds prevents altitude throttle spikes from destabilizing attitude.
3. **Turning radius compression is measurable.** At full flywheel charge (67%→100%): r_min drops from 8.8 m to 4.4 m — a 50% tighter arc at the same bank angle limit.
4. **Regen is modest but real.** ~16 J per 20m×20m circuit ≈ 0.0044 Wh. Meaningful at scale (multi-circuit survey missions, repeated descents).
5. **Gimbal authority stays within ±5°** during normal cruise — well within the ±15° servo range. Full deflection reserved for aggressive attitude recovery.
6. **Wind/noise robustness (added 2026-06-09):** stable through 8 m/s wind + 3 m/s gusts + sensor noise (`--wind 8 --gust 3 --noise`). Altitude holds ~0.3 m mean error under 5 m/s wind with baro-class altitude estimation. Modelling note: feeding GPS-class z-bias to the controller overstated altitude error 4× — no controller fixes an estimation bias, so the noise model uses baro-class z (the EKF reality). Position x/y keep GPS-class bias.

### Controller Parameters (validated in sim)

```python
# Position loop
pos_Kp = 0.5      # (m/s^2)/m
pos_Kd = 1.0      # (m/s^2)/(m/s)
a_max  = 3.0      # m/s^2 horizontal limit
TILT_MAX = 0.35   # rad (~20 deg)

# Attitude loop (omega_n = 5 rad/s, zeta = 0.8)
att_Kp = 25.0     # (rad/s^2)/rad
att_Kd =  8.0     # (rad/s^2)/(rad/s)

# Altitude (PI+D)
alt_Kp = 0.5
alt_Ki = 0.04
alt_Kd = 0.3
```

---

## Phase 0.75 — Software-in-the-Loop Validation (Complete)

**Goal:** Prove every piece of flight software against real ArduCopter before
any hardware exists. Setup and procedures: [SITL_TESTING.md](SITL_TESTING.md).

| Test | Result | Date |
|---|---|---|
| Momentum manager vs ArduCopter SITL (`src/momentum-manager/sitl_test.py`) | 7/7 PASS. Dubins circuit tracked, REGEN/DISCHARGE triggered, telemetry staleness 96 ms | 2026-06-09 |
| Lua script on stock firmware (`src/fc-lua/sitl_lua_test.py`) | 6/6 PASS. Gains scaled at 20k RPM, overspeed and stale-telemetry failsafes | 2026-06-09 |
| Lua script + firmware feed-forward patch (same test, patched SITL) | 7/7 PASS. `FWC: firmware feed-forward active` | 2026-06-09 |
| SITL flight demo (`tools/sitl_fly_demo.py`, checked with `tools/read_last_flight.py`) | Arm, take off, hover, land | 2026-06-10 |
| Pytest suite in CI (`tests/`) | 10 tests: sampler, planner, circuit, windy circuit | 2026-09-24 |

**Known gaps** that SITL cannot close:
- The VESC is still simulated (`VESCInterface(sim=True)`). Regen numbers are estimates.
- `FWC_ACT_NM` is a placeholder (0.8) until measured on the real airframe.

---

## Phase 1 — Mechanical + Basic Flight (Weeks 1–6)

**Goal:** Disc frame flies stably as a conventional quad. No flywheel yet.

### Week 1–2: CAD
- [x] Bottom plate design — v02 generated parametrically, 164 g (was 255 g);
      `tools/generate_cad_v02.py` (2026-06-09)
- [x] Top plate design — v02 R80 electronics tray, 56 g (was 201 g)
- [x] Motor mount pad geometry validated (30×30 pads at R185, 16×16 M3)
- [x] DXF cut profiles exported (`cad/dxf/`) — SendCutSend, CF .118″/.079″
- [ ] Order plates (add fillets in Fusion first; see FRAME_SPEC v02 notes)
- [x] Flywheel rotor STEP exists (`cad/stl/step/flywheel_rotor_v01.step`)
- [ ] Decide rotor: v01 default (I = 1.24e-4) or v02 heavy (I = 1.78e-4).
      v02 means updating the inertia constants listed in STRUCTURE.md
- [ ] Order rotor **and containment cup** from PCBWay CNC (6061-T6), one order
- [ ] Update flywheel boss flange: bolt circle 55 → 62 mm (Fusion)
- [ ] Print landing legs in TPU

### Week 3: Parts arrival + prep
- [ ] Order all Phase 1 electronics (motors, ESC, FC, props, battery)
- [ ] Inspect CF plates for delamination, measure true dimensions
- [ ] Tap M3 holes in carbon fiber (use thread insert or tap carefully)
- [ ] Test fit all components dry (no solder yet)

### Week 4: Assembly
- [ ] Solder ESC stack
- [ ] Mount FC on rubber grommets
- [ ] Install motors, check rotation direction
- [ ] Wire battery leads with XT60
- [ ] Flash ArduCopter 4.5 to H743
- [ ] Initial param config (frame type: X, motor layout)

### Week 5: Ground testing
- [ ] Motor direction test (props off)
- [ ] ESC calibration
- [ ] Accelerometer + compass calibration
- [ ] PID autotune (props on, tethered or on bench stand)
- [ ] Verify no vibration resonance at hover throttle

### Week 6: First flight
- [x] Rehearse arm, takeoff, hover, land in SITL (`tools/sitl_fly_demo.py`, 2026-06-10)
- [ ] Hover test in open area (low altitude, tethered)
- [ ] Validate disc frame CoG in flight
- [ ] Log IMU data — compare vibration profile vs conventional quad
- [ ] Document: does frame show gyroscopic stabilization contribution?

**Phase 1 Exit Criteria:** Stable hover for 5+ minutes, clean IMU logs

---

## Phase 2 — Flywheel Integration (Weeks 7–10)

**Goal:** Flywheel spinning and measurable energy recovery on descent.

### Week 7: Flywheel mechanical
- [ ] Receive machined rotor and containment cup from PCBWay
- [x] Burst containment designed — `containment_cup_v01` (one-piece, 6061;
      see FLYWHEEL_SPEC) — ordered with the rotor in Phase 1
- [ ] Balance rotor (static balance on mandrel)
- [ ] Press-fit angular contact bearings
- [ ] Install flywheel motor (RS2205) into rotor bore
- [ ] Mount assembly on boss, torque retention bolts
- [ ] Spin-pit test per FLYWHEEL_SPEC protocol (cup mandatory) before
      the assembly goes anywhere near the airframe

### Week 8: VESC integration
- [ ] Install VESC Tool on laptop
- [ ] Motor detection wizard (RS2205 on VESC)
- [ ] Configure RPM control mode (target 18,000 RPM initially)
- [ ] Configure regenerative braking limits
- [ ] Bench test: spin up, brake, measure energy returned to bench supply
- [ ] Replace the simulated `VESCInterface` in `momentum_manager.py` with the
      real UART driver, and re-run the SITL test with live VESC data

### Week 9: Gimbal servos
- [ ] Print gimbal brackets (PETG)
- [ ] Install Savöx servos on 2 motor arms
- [ ] Connect to H743 servo outputs
- [ ] Test manual vectoring via RC input

### Week 10: Flight integration
- [ ] Fly with flywheel active (non-regenerative first)
- [ ] Measure hover stability improvement vs Phase 1 logs
- [ ] Enable regen: fly descent profile, log VESC energy counters
- [ ] Calculate actual vs theoretical energy recovery

**Phase 2 Exit Criteria:** Measurable energy recovery on 10m descent profile

---

## Phase 3 — Companion Computer + Pathfinding (Weeks 11–14)

**Goal:** Autonomous arc-path mission with momentum-aware planning.

### Week 11: Companion computer setup
- [ ] Flash Armbian on Orange Pi Zero 3
- [ ] Install MAVProxy + pymavlink
- [ ] Establish UART link to H743 (SERIAL2)
- [ ] Verify telemetry stream in Python on hardware
      (already proven over TCP against SITL; only the UART link is new)

### Week 12: Dubins path implementation
- [x] Implement Dubins path library (inline LSL/RSR/LSR/RSL — no external dep)
- [x] Add momentum constraint: turn radius scales with flywheel charge fraction
- [x] Compute turn radius adjustment from flywheel energy level
- [x] Generate test waypoint set (5-point circuit) — validated in simulation
- [ ] Port to companion computer, query live VESC state via UART

### Week 13: MAVLink integration
- [x] Send Dubins-generated waypoints to ArduCopter via MAVLink — validated in SITL
- [ ] Override default straight-line interpolation
- [x] Test in SITL (Software In The Loop) simulation first — see [SITL_TESTING.md](SITL_TESTING.md)
      (7/7 checks pass: Dubins circuit tracked, REGEN/DISCHARGE state machine
      triggers on real descent/climb, telemetry staleness < 100 ms)
- [ ] Log commanded vs actual path

### Week 14: Full system flight test
- [ ] Fly 5-point mission with arc pathfinding enabled
- [ ] Compare energy consumption vs same mission with straight paths
- [ ] Log: flywheel RPM, VESC energy, battery voltage sag, total flight time
- [ ] Calculate real efficiency gain

**Phase 3 Exit Criteria:** Measurable autonomy improvement in arc vs waypoint mission

---

## Phase 4 — Optimization (Ongoing)

- [x] Firmware gyroscopic feed-forward (AC_AttitudeControl patch + Lua binding,
      validated in patched SITL 2026-06-09 — see src/firmware-patch/)
- [ ] Tune `FWC_ACT_NM` on the real airframe: start at 0.8, compare commanded
      vs achieved rates during flywheel spin-up. Keep `FWC_ENABLE=2` until then
- [ ] Flash the patched firmware to the H743 (currently SITL only)
- [ ] PID retuning with flywheel active (gyroscopic coupling compensation)
- [ ] VESC regen profile optimization per mission type
- [ ] Pathfinding extension: 3D arc paths (altitude changes)
- [ ] Weight reduction iteration (redesign heavy components)
- [ ] Endurance benchmark: timed hover comparison vs equivalent X-quad
- [ ] Consider: paper / technical writeup submission

### Repository health
- [x] Pytest suite (`tests/`) run in CI, plus headless sim run (2026-09-24)
- [x] Planner no longer needs the unbuildable `dubins` C library (2026-09-24)
- [x] MIT LICENSE file added (2026-09-24)
- [x] Unrelated football model moved to its own repository (2026-09-24)
- [ ] Turn the SITL scripts into an opt-in pytest job (needs SITL in CI)
- [ ] Add Lua script unit tests that run without SITL

---

## Milestone Summary

| Milestone | Target Week | Validation | Status (2026-09-24) |
|---|---|---|---|
| Simulation validated | — | Circuit, figure-8, lawnmower, wind + noise | Done 2026-06-09 |
| Flight software validated in SITL | — | 7/7, 6/6, 7/7 test runs + flight demo | Done 2026-06-10 |
| Frame flying stable | 6 | 5min hover, clean logs | Waiting on parts order |
| Flywheel measurable recovery | 10 | VESC energy log on descent | Not started |
| Arc pathfinding operational | 14 | Circuit mission vs waypoint | Proven in SITL, hardware pending |
| Efficiency benchmark | 16 | vs baseline X-quad same motors | Not started |

# Development Roadmap — GyroDrone

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
| Regen energy recovered | ~17 J per circuit |
| Turning radius (67% FW charge) | 5.9 m (vs 8.8 m empty) |
| Max roll during arc turns | < 1° (gyroscopic stabilization active) |

### Run the Simulation

```bash
python -m venv .venv
.venv/Scripts/pip install numpy matplotlib

# Default circuit
.venv/Scripts/python src/simulation/gyrodrone_sim.py

# Other profiles
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission figure8
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission lawnmower
.venv/Scripts/python src/simulation/gyrodrone_sim.py --no-regen   # FESS disabled comparison
.venv/Scripts/python src/simulation/gyrodrone_sim.py --dt 0.005   # high-fidelity
```

### Key Findings

1. **Gyroscopic feed-forward is mandatory.** Without canceling flywheel angular momentum coupling, pitch maneuvers induce ~10° spurious roll. The `tau_r += L_fw*q` term in the controller eliminates this.
2. **Wrench allocation decouples throttle from attitude.** Mapping desired torques (Nm) directly to motor speeds prevents altitude throttle spikes from destabilizing attitude.
3. **Turning radius compression is measurable.** At full flywheel charge (67%→100%): r_min drops from 8.8 m to 4.4 m — a 50% tighter arc at the same bank angle limit.
4. **Regen is modest but real.** ~17 J per 20m×20m circuit ≈ 0.005 Wh. Meaningful at scale (multi-circuit survey missions, repeated descents).
5. **Gimbal authority stays within ±5°** during normal cruise — well within the ±15° servo range. Full deflection reserved for aggressive attitude recovery.

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

## Phase 1 — Mechanical + Basic Flight (Weeks 1–6)

**Goal:** Disc frame flies stably as a conventional quad. No flywheel yet.

### Week 1–2: CAD
- [ ] Bottom plate design in Fusion 360 (from FRAME_SPEC.md)
- [ ] Top plate design
- [ ] Motor mount pad geometry validation
- [ ] Export DXF → order from PCBWay or SendCutSend
- [ ] Design flywheel rotor STEP file → order from PCBWay CNC
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
- [ ] Hover test in open area (low altitude, tethered)
- [ ] Validate disc frame CoG in flight
- [ ] Log IMU data — compare vibration profile vs conventional quad
- [ ] Document: does frame show gyroscopic stabilization contribution?

**Phase 1 Exit Criteria:** Stable hover for 5+ minutes, clean IMU logs

---

## Phase 2 — Flywheel Integration (Weeks 7–10)

**Goal:** Flywheel spinning and measurable energy recovery on descent.

### Week 7: Flywheel mechanical
- [ ] Receive machined rotor from PCBWay
- [ ] Balance rotor (static balance on mandrel)
- [ ] Press-fit angular contact bearings
- [ ] Install flywheel motor (RS2205) into rotor bore
- [ ] Mount assembly on boss, torque retention bolts

### Week 8: VESC integration
- [ ] Install VESC Tool on laptop
- [ ] Motor detection wizard (RS2205 on VESC)
- [ ] Configure RPM control mode (target 18,000 RPM initially)
- [ ] Configure regenerative braking limits
- [ ] Bench test: spin up, brake, measure energy returned to bench supply

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
- [ ] Verify telemetry stream in Python

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

- [ ] PID retuning with flywheel active (gyroscopic coupling compensation)
- [ ] VESC regen profile optimization per mission type
- [ ] Pathfinding extension: 3D arc paths (altitude changes)
- [ ] Weight reduction iteration (redesign heavy components)
- [ ] Endurance benchmark: timed hover comparison vs equivalent X-quad
- [ ] Consider: paper / technical writeup submission

---

## Milestone Summary

| Milestone | Target Week | Validation |
|---|---|---|
| Frame flying stable | 6 | 5min hover, clean logs |
| Flywheel measurable recovery | 10 | VESC energy log on descent |
| Arc pathfinding operational | 14 | Circuit mission vs waypoint |
| Efficiency benchmark | 16 | vs baseline X-quad same motors |

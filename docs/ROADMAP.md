# Development Roadmap — GyroDrone

---

## Phase 0 — Architecture (Complete)
- [x] Physics validation (gyroscopic effect, FESS math, Dubins path)
- [x] Component selection and BOM
- [x] CAD specifications drafted
- [x] GitHub documentation structure

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
- [ ] Implement Dubins path library (use `dubins` Python package as base)
- [ ] Add momentum constraint: query flywheel VESC state via UART
- [ ] Compute turn radius adjustment from flywheel energy level
- [ ] Generate test waypoint set (5-point circuit)

### Week 13: MAVLink integration
- [ ] Send Dubins-generated waypoints to ArduCopter via MAVLink
- [ ] Override default straight-line interpolation
- [ ] Test in SITL (Software In The Loop) simulation first
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

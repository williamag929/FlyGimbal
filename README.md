# GyroDrone — Inertia-Optimized Disc UAV

> *A UAV that works with physics, not against it.*

![Status](https://img.shields.io/badge/status-prototype--phase--1-orange)
![Budget](https://img.shields.io/badge/budget-under%20%24500-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Platform](https://img.shields.io/badge/FC-ArduCopter%20%2F%20Matek%20H743-red)

---

## What Is This?

GyroDrone is an open-source UAV project that integrates three physics principles typically ignored in commercial drones:

1. **Gyroscopic stabilization** — disc-shaped frame distributes mass at the perimeter, creating natural angular momentum stability
2. **Flywheel energy recovery (FESS)** — kinetic energy from descents and braking is stored and reused via a VESC-controlled flywheel
3. **Momentum-aware pathfinding** — Dubins Path algorithm modified to exploit existing momentum instead of canceling it

The goal: a drone that is **more efficient, quieter, and more stable** than conventional quad designs — at hobbyist budget.

---

## Key Differentiators vs. Conventional Quads

| Feature | Conventional Quad | GyroDrone |
|---|---|---|
| Frame shape | X or H | Disc (400mm diameter) |
| Stability source | Software PID | Physics + PID |
| Energy recovery | None | Flywheel FESS via VESC |
| Flight path planning | Stop-and-go waypoints | Continuous arc (Dubins) |
| Thrust vectoring | RPM delta only | Gimbal-mounted motors |
| Mass distribution | Central cluster | Perimeter-biased ring |

---

## Project Status

- [x] Phase 0 — Concept & Architecture
- [x] Phase 0.5 — Physics Simulation (incl. wind/gust/sensor-noise robustness)
- [ ] Phase 1 — Frame CAD + Basic Flight (current: v02 CAD generated, parts ordering next)
- [ ] Phase 2 — Flywheel Integration (containment cup modeled — machine before spin-up)
- [ ] Phase 3 — Companion Computer + Pathfinding
- [ ] Phase 4 — Full System Tuning & Benchmarking

**Software validated ahead of hardware** (all against real ArduCopter SITL):
- [x] Momentum manager ↔ ArduCopter integration — 7/7 checks ([SITL_TESTING.md](docs/SITL_TESTING.md))
- [x] FC Lua applet: flywheel gain scheduling + failsafes — runs on stock firmware
- [x] ArduPilot firmware patch: true gyroscopic feed-forward in the 400 Hz rate loop — 7/7 incl. live momentum injection ([src/firmware-patch/](src/firmware-patch/README.md))

![prototype](cad/preview_assembly.png)

---

## Repository Structure

```
FlyGimbal/
├── README.md
├── .github/                        # CI + issue templates
├── docs/
│   ├── PHYSICS.md                  # Theoretical foundation
│   ├── BOM.md                      # Full bill of materials
│   ├── BUILD_GUIDE.md              # Step-by-step assembly
│   ├── ROADMAP.md                  # Development timeline
│   ├── SITL_TESTING.md             # SITL setup + validation results
│   └── CONTRIBUTING.md
├── cad-specs/
│   ├── FRAME_SPEC.md               # Frame design parameters (v01 + v02)
│   ├── FLYWHEEL_SPEC.md            # Rotor, bearings, burst containment
│   └── GIMBAL_SPEC.md              # Thrust-vector motor gimbal spec
├── cad/                            # Released geometry — see cad/README.md
│   ├── stl/ stl/step/ dxf/         # meshes, CNC solids, plate cut profiles
│   └── preview_assembly.png        # rendered prototype
├── tools/
│   ├── generate_cad_v02.py         # parametric part generator (CadQuery)
│   ├── render_assembly.py          # prototype render from the STLs
│   └── stl_check.py                # mass / inertia audit (exact integrals)
└── src/
    ├── simulation/gyrodrone_sim.py        # 6-DOF physics sim (+wind/noise)
    ├── pathfinding/dubins_momentum.py     # momentum-aware Dubins planner
    ├── momentum-manager/                  # companion-computer daemon + SITL test
    ├── fc-lua/flywheel_coupling.lua       # FC applet: gain sched + FF bridge
    └── firmware-patch/                    # ArduPilot gyroscopic feed-forward
```

---

## Quick Start

### Run the Physics Simulation

No hardware required. Validates the full system before building.

```bash
# Install dependencies
python -m venv .venv
.venv/Scripts/pip install numpy matplotlib   # Windows
# or: .venv/bin/pip install numpy matplotlib  # Linux/Mac

# Run default circuit mission (5 waypoints, 20m x 20m)
.venv/Scripts/python src/simulation/gyrodrone_sim.py

# Other mission profiles
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission figure8
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission lawnmower
.venv/Scripts/python src/simulation/gyrodrone_sim.py --mission square

# Compare with/without flywheel energy recovery
.venv/Scripts/python src/simulation/gyrodrone_sim.py --no-regen

# Real-world stress: wind + gusts + sensor noise (GPS bias, IMU noise)
.venv/Scripts/python src/simulation/gyrodrone_sim.py --wind 5 --noise
.venv/Scripts/python src/simulation/gyrodrone_sim.py --wind 8 --gust 3 --noise

# Higher fidelity timestep
.venv/Scripts/python src/simulation/gyrodrone_sim.py --dt 0.005
```

Outputs: telemetry summary to console + `gyrodrone_simulation.png` (8-panel dashboard).

### Prerequisites (Hardware Build)
- Fusion 360 (free for hobbyists) for CAD
- ArduCopter 4.5+ flashed on Matek H743
- Python 3.10+ for companion computer scripts
- VESC Tool for flywheel ESC configuration

### Phase 1 Build
See [BUILD_GUIDE.md](docs/BUILD_GUIDE.md) for full assembly instructions.

---

## Physics Background

The core insight: a conventional drone **fights** inertia on every maneuver. GyroDrone **redirects** it.

When a disc-shaped body spins, it resists changes to its orientation (gyroscopic effect). This resistance — typically seen as a problem — becomes a stabilization asset. The flight controller does less corrective work, spending that headroom on precision.

For the full theoretical treatment, see [PHYSICS.md](docs/PHYSICS.md).

---

## Contributing

This is a solo R&D project but PRs and issues are welcome, especially for:
- Alternative flywheel rotor geometries
- VESC regenerative braking tuning
- Dubins Path momentum constraint improvements

---

## License

MIT — build it, modify it, fly it.

---

*Built from first principles. No shortcuts.*

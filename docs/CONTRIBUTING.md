# Contributing to FlyGimbal

First off — thanks for taking the time to contribute to an open hardware project. This is experimental R&D, so all skill levels are welcome as long as you bring rigor.

---

## What We're Looking For

The highest-value contributions right now are in these areas:

### 🔧 Mechanical / CAD
- Alternative flywheel rotor geometries (different mass distributions, materials)
- Improved motor gimbal bracket designs (lower weight, better vibration isolation)
- Landing gear concepts that don't compromise the disc aerodynamics
- FEA analysis of the carbon fiber frame under motor load

### ⚡ Firmware / Electronics
- ArduCopter parameter files tuned for disc frame dynamics
- VESC regenerative braking profiles optimized for different mission types
- Wiring schematics (KiCad preferred)
- ESC telemetry integration improvements

### 🐍 Software (Python)
- Dubins path extensions: 3D arc paths with altitude changes
- Flywheel state estimator improvements (Kalman filter on RPM noise)
- MAVLink mission upload reliability fixes
- SITL (Software In The Loop) simulation test suite

### 📐 Physics / Analysis
- Gyroscopic coupling compensation in PID tuning
- Energy recovery efficiency benchmarks
- Comparison against baseline X-quad (same motors, same battery)

---

## How to Contribute

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/FlyGimbal.git
cd FlyGimbal
```

### 2. Create a Branch

Use descriptive branch names:

```bash
git checkout -b fix/dubins-radius-constraint
git checkout -b feat/vesc-kalman-filter
git checkout -b docs/wiring-diagram-phase2
```

### 3. Set Up Python Environment

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 4. Make Your Changes

- Keep commits atomic — one logical change per commit
- Write clear commit messages (see format below)
- If touching physics math, show your work in comments or docs

### 5. Test Before Submitting

```bash
# Run the path planner in sim mode — should complete without errors
python src/pathfinding/dubins_momentum.py --sim

# Run tests if applicable
pytest tests/ -v
```

### 6. Open a Pull Request

- Target branch: `master`
- Fill out the PR template (auto-populated)
- Link any related issues with `Closes #N`

---

## Commit Message Format

```
type(scope): short description

Longer explanation if needed. Wrap at 72 chars.
Reference issues: Closes #12, Related #8
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
```
feat(pathfinding): add altitude-aware 3D Dubins extension
fix(vesc): clamp regen current below 5000 RPM threshold
docs(frame-spec): add FEA stress analysis results
```

---

## Reporting Issues

Use GitHub Issues. Include:

- **Phase** you're in (1 / 2 / 3)
- **What you expected** vs **what happened**
- **Hardware config** if relevant (FC version, motor model, etc.)
- **Logs** — ArduCopter .bin logs or Python tracebacks

For build questions, open a Discussion instead of an Issue.

---

## CAD Contributions

- Preferred format: **Fusion 360 (.f3d)** or **STEP (.step)**
- Include a rendered screenshot in your PR
- Document key dimensions in the relevant `cad-specs/*.md` file
- If modifying the frame: re-validate that CG stays within ±3mm of geometric center

---

## Code Style

Python:
- PEP 8 compliance (use `black` formatter if possible)
- Type hints on all function signatures
- Docstrings on all public functions/classes
- No magic numbers — use named constants at module level

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License that covers this project.

---

## Questions?

Open a [GitHub Discussion](https://github.com/williamag929/FlyGimbal/discussions) — not an Issue — for general questions, ideas, or build help.

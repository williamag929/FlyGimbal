# Physics Foundation — GyroDrone

> Theoretical basis for the three core design decisions.

---

## 1. Gyroscopic Stabilization

### Angular Momentum

A rotating body has angular momentum **L**:

```
L = I × ω

Where:
  I = moment of inertia (kg·m²)
  ω = angular velocity (rad/s)
  L = angular momentum vector (along spin axis)
```

Angular momentum is conserved unless an external torque acts on the system. This means a spinning disc **resists changes to its orientation** — the faster it spins and the more mass at the outer radius, the stronger this resistance.

### Why Disc Shape?

For a ring of mass m at radius r:
```
I_ring = m × r²
```

For the same mass distributed as a solid disc:
```
I_disc = ½ × m × r²
```

A ring has **2× the moment of inertia** of a solid disc of equal mass. GyroDrone's perimeter-heavy frame approximates a ring, maximizing I per kilogram.

### Precession vs. Tumbling

When gravity applies a torque τ to the spin axis, a gyroscope doesn't fall — it precesses:

```
Precession rate: Ω = τ / L = (mgr) / (Iω)

Higher ω (faster spin) → slower precession → more stable
Higher I (more mass at rim) → slower precession → more stable
```

The disc frame contributes gyroscopic stability even without the flywheel. The flywheel adds a second, controllable gyroscopic axis.

---

## 2. Flywheel Energy Storage (FESS)

### Kinetic Energy in Rotation

```
KE = ½ × I × ω²
```

At 20,000 RPM with the as-built v01 rotor (I ≈ 1.24 × 10⁻⁴ kg·m², exact
tetrahedron integral of flywheel_rotor_v01.stl):
```
ω = 20,000 × 2π / 60 = 2,094 rad/s
KE = ½ × 1.24e-4 × 2094² ≈ 272 J ≈ 0.076 Wh
```

### Energy Recovery Scenario

During a 10-meter descent at 2 m/s:
```
Gravitational PE lost = mgh = 1.2 kg × 9.8 × 10 = 117.6 J

Without recovery: 117.6 J dissipated as heat in motor braking
With FESS (70% efficiency): ~82 J → flywheel
  → From 15,000 RPM (ω = 1571 rad/s):
    ω_new = √(ω² + 2×82/1.24e-4) = √(1571² + 1.323e6) ≈ 1947 rad/s
  → RPM increase: +3,600 RPM from the descent alone
```

On ascent, that stored energy is released back — reducing battery draw proportionally.

### Why VESC for Regeneration?

Standard BLHeli_32 ESCs cannot do true regenerative braking — they dissipate energy as heat. The VESC (Variable Speed Controller) implements a full 4-quadrant motor driver:
- Quadrant 1: Motor driving (spin up)
- Quadrant 2: Motor braking / generating (spin down → energy back)
- This is the same principle as regenerative braking in electric vehicles.

---

## 3. Momentum-Aware Pathfinding

### The Problem with Conventional Waypoints

Standard drone flight planners move between discrete waypoints:
```
A → [decelerate] → B → [accelerate] → C
        ↑
    Energy wasted here (twice per segment)
```

At every waypoint transition, kinetic energy is destroyed and rebuilt. For a 1.2kg drone at 5 m/s:
```
KE = ½ × 1.2 × 5² = 15 J wasted per stop
At 10 waypoints: 150 J = ~0.042 Wh per mission
```

### Dubins Path

A Dubins path is the shortest curve connecting two configurations (position + heading) using only:
- Left turns (L)
- Right turns (R)
- Straight segments (S)

Any path is one of: {LSL, LSR, RSL, RSR, RLR, LRL}

```python
# Dubins path minimum turning radius:
r_min = v² / (g × tan(bank_angle_max))

# At 5 m/s, 30° max bank:
r_min = 25 / (9.8 × tan(30°)) = 25 / 5.66 ≈ 4.4 meters
```

The drone never makes sharp corners — it always follows the minimum-radius arc between waypoints, **preserving velocity throughout the mission**.

### Momentum Constraint Extension

Standard Dubins assumes constant speed. GyroDrone's planner adds:

```
Constraint: curvature_max = f(v_current, flywheel_state)

If flywheel is at high RPM (energy available):
  → Allow tighter turns (spend gyroscopic stabilization budget)

If flywheel is at low RPM (energy depleted):
  → Enforce gentler turns (protect attitude stability)
```

This creates a **coupled energy-path planning system** — the flight path is dynamically adjusted based on available stored kinetic energy.

---

## 4. Combined System Efficiency Estimate

Compared to an equivalent conventional X-quad (same motors, same battery):

| Factor | Conventional | GyroDrone | Delta |
|---|---|---|---|
| Stabilization power | ~8% of total | ~3% (physics assists) | -5% |
| Waypoint energy waste | ~12% | ~2% (arc paths) | -10% |
| Descent energy recovery | 0% | ~6% recovered | +6% |
| Total theoretical gain | — | — | **+21%** |

**Estimated autonomy improvement: 15–25%** depending on mission profile.
Missions with many altitude changes and directional transitions benefit most.

---

## References

- Goldstein, H. *Classical Mechanics* — gyroscope precession (Ch. 5)
- Dubins, L.E. (1957). *On Curves of Minimal Length...* — American Journal of Mathematics
- Bolund, B. et al. (2007). *Flywheel energy storage* — Renewable and Sustainable Energy Reviews
- ArduPilot documentation — MAVLink UART interface, Lua scripting API

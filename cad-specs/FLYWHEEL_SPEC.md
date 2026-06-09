# Flywheel (FESS) Specification — GyroDrone v0.1

> Kinetic energy storage and gyroscopic stabilization subsystem.

---

## Design Goals

| Goal | Target |
|---|---|
| Stored energy at 20,000 RPM | ~254 J (0.071 Wh); ~0.05 Wh recoverable at 72% VESC regen |
| Gyroscopic contribution | Measurable precession resistance (L ≈ 0.24 N·m·s at 20k RPM) |
| Mass | ≤ 120g (rotor + motor + bearing) |
| Diameter | ≤ 80mm (fits 110mm bay with clearance) |
| Height | ≤ 22mm total stack |

> **Honest energy note:** the flywheel is NOT a net energy-recovery win — the
> system's added mass costs more hover power than regen returns. Its real value
> is gyroscopic stabilization and momentum-aware tight turns; regen is a
> secondary experiment.

---

## Rotor Geometry

### Profile: Annular Disc (Ring Rotor)

Mass concentrated at outer radius maximizes I per unit mass.

```
Cross-section view:

     ├──── 80mm ────┤
     ┌──┐        ┌──┐   ← Outer rim: 10mm wide × 15mm tall
     │  │        │  │     (primary mass zone)
     │  └────────┘  │   ← Center web: 4mm thick
     │   ↑        ↑ │
     │  inner    inner│
     │  30mm dia      │
     └────────────────┘
          bottom
```

### Dimensions

| Feature | Dimension |
|---|---|
| Outer diameter | 80 mm |
| Inner bore | 30 mm (motor shaft interface) |
| Outer rim width | 10 mm |
| Outer rim height | 15 mm |
| Center web thickness | 4 mm |
| Total height | 15 mm |
| Material | Aluminum 6061-T6 |
| Surface finish | Anodized (balance marking) |

### Mass (as-built, measured from flywheel_rotor_v01.stl)
```
STL solid volume:    43.7 cm³
Mass (6061-T6, 2.70 g/cm³):  ~118 g  ✓ meets ≤120g goal
Post-balance target: ≤ 118g (relief holes only remove material)
```

### Moment of Inertia (as-built v01 rotor)
```
Measured from flywheel_rotor_v01.stl solid geometry:
I ≈ 1.16 × 10⁻⁴ kg·m²

At 20,000 RPM (ω = 2094 rad/s):
L = I × ω = 1.16e-4 × 2094 = 0.243 N·m·s

Stored KE = ½ × I × ω²
          = ½ × 1.16e-4 × 2094²
          = ~254 J ≈ 0.071 Wh

Note: Real energy recovery efficiency via VESC ~70-80%
Effective recoverable: ~0.05 Wh per charge cycle

This value (1.16e-4) is the single source of truth — used by
gyrodrone_sim.py (FW_I), momentum_manager.py (FLYWHEEL_I),
dubins_momentum.py, and the FWC_INERTIA Lua parameter default.
A heavier v02 rotor (rim 15→18mm tall: ~145g, I≈1.76e-4, 386 J)
remains an option if more gyroscopic authority is needed — update
all four software constants together if built.
```

---

## Balancing Requirements

**Critical** — an unbalanced flywheel at 20,000 RPM destroys bearings and saturates the IMU.

```
Balance standard target: G2.5 (ISO 1940-1)
Allowable residual imbalance at 20,000 RPM:
  U_per = G × m / ω
        = 2.5 × 0.145 / 2094
        = 0.000173 kg·m = 0.173 g·mm

Practical method:
1. Machine rotor, mark 0° reference
2. Static balance on knife-edge mandrel
3. Mark heavy spot, drill relief holes (2mm drill, max 3mm deep)
   in outer rim bottom face
4. Re-check — repeat until within spec
5. Dynamic balance if available (preferred)
```

---

## Motor Selection

```
T-Motor MN3508 580KV
  KV:           580 RPM/V
  At 4S (14.8V nominal): 580 × 14.8 = 8,584 RPM (no load)
  
  → Insufficient for 20,000 RPM target at 4S

REVISED: Use 6S battery for flywheel motor only
  At 6S (22.2V): 580 × 22.2 = 12,876 RPM → still low

BETTER OPTION:
  Sunnysky X2212 980KV
  At 6S: 980 × 22.2 = 21,756 RPM ✓
  Weight: 52g
  Price: ~$18

  OR:

  Emax RS2205 2300KV (race motor, high RPM)
  At 4S: 2300 × 14.8 = 34,040 RPM → reduce via VESC throttle limit
  More RPM headroom = better energy storage
  Weight: 30g
  Price: ~$15

Recommendation: Emax RS2205 2300KV + VESC throttle cap at 22,000 RPM
```

---

## Bearing Selection

Standard radial bearings fail under gyroscopic axial loads.

```
Required: Angular Contact Bearings

Spec: 7000C angular contact (NOT 6000-series — those are deep-groove
      radial bearings despite similar dimensions; wrong part for this load)
  ID: 10mm (motor shaft)
  OD: 26mm
  Width: 8mm
  Contact angle: 15° (C suffix — handles combined radial + axial load)
  Speed rating: verify ≥ 24,000 RPM oil-lubricated (7000C typically ~28k)

Quantity: 2× per flywheel (top + bottom of rotor)
Preload: Light preload pair (face-to-face DB configuration)
Lubrication: Light spindle oil (NOT grease — too viscous at 20kRPM)
Source: NSK, SKF, or NTN (avoid generic Chinese at this RPM)
Price: ~$8–12 per bearing
```

---

## VESC Configuration

The VESC 4.12 handles:
1. **Spin-up** — accelerate flywheel to target RPM
2. **Maintenance** — hold RPM against bearing friction losses
3. **Regenerative braking** — controlled deceleration → energy back to battery

```
VESC Tool settings:

Motor type:       BLDC (sensored if motor has hall sensors)
                  or FOC (better efficiency, requires tuning)

Current limits:
  Motor max:      25A (spin-up)
  Motor min:      -15A (regenerative)
  Battery max:    20A
  Battery min:    -10A (regen back to main pack)

RPM limits:
  Max ERPM:       20,000 × pole_pairs   (matches FLYWHEEL_RPM_MAX in software)
                  (RS2205 = 7 pole pairs → 140,000 ERPM)
  Min ERPM:       1,000 (prevent stall detection issues)

Control mode:     RPM control (PID speed loop)
  Target RPM:     20,000 nominal
  Regen trigger:  When main ESC stack signals deceleration
                  (via UART or PWM signal from companion computer)

Regen profile:
  Brake current:  -12A (gentle — preserve bearing life)
  Min regen RPM:  5,000 (below this, friction > gain)
```

---

## Structural Mount

```
Bottom mount boss (3D printed PETG or machined Al):

  Bolts to bottom plate via 4× M3 at 55mm radius
  Motor faces DOWN (rotor spins below bottom plate level)
  
  Reason: Lower CG, flywheel gyroscopic axis = vertical
           (same axis as drone yaw — maximizes stabilization effect)

Clearance:
  Rotor bottom to ground (with landing legs): 18mm minimum
  Landing leg height must account for this
```

---

## Burst Containment (REQUIRED before first spin-up)

The rotor stores ~254 J at 20,000 RPM with a rim speed of 84 m/s — comparable
to a rifle round, centimeters from a LiPo. The PETG mount boss will NOT
contain a liberated rim fragment. A dedicated containment part is mandatory.

```
Part: containment_ring_v01 (NOT YET MODELED — design before Phase 2)

Geometry:
  Ring lining the 110mm frame bay around the 80mm rotor
  Inner diameter: 86 mm  (3mm radial clearance to rotor)
  Wall thickness: 3 mm   (6061-T6) or 1.5 mm (mild steel)
  Height:         20 mm  (covers full rotor + margin)
  Top cover:      2 mm plate, bolted, with center hole for shaft

Sizing rationale (fragment containment, not hoop stress):
  Worst case: 1/3 rim fragment (~30g) at 84 m/s = ~105 J
  3mm 6061 ring absorbs >300 J/cm² in plastic deformation at this
  scale — adequate margin. Steel preferred if mass budget allows.

Test protocol (spin pit):
  1. First spin-up: rotor + containment in a sandbag-lined bucket,
     outdoors, nobody in the plane of rotation, VESC tethered
  2. Step RPM: 5k → 10k → 15k → 20k, 2 min dwell each
  3. Listen/log for bearing resonance; abort on any vibration spike
  4. Only after a clean 20k run does the assembly go on the airframe
```

---

## Fabrication Options

```
Option A — Local machine shop
  Material: 6061-T6 rod stock, 85mm diameter
  Operations: Face, bore, profile, drill
  Est. cost: $25–40 depending on shop
  Lead time: 1–3 days

Option B — Xometry.com (online CNC)
  Upload STEP file → instant quote
  Est. cost: $35–55 (quantity 1)
  Lead time: 5–7 days
  Finish: Anodize option available (+$15)

Option C — PCBWay CNC service
  Cheaper than Xometry for single parts
  Est. cost: $20–35
  Lead time: 10–15 days (from China)
  
Recommended for prototype: PCBWay (cost) or local shop (speed)
```

---

## Files to Generate

- [x] `flywheel_rotor_v01.step` — STEP for CNC machining (in cad/stl/step/)
- [x] `flywheel_rotor_v01.stl` — STL for reference/mockup (in cad/stl/)
- [x] `flywheel_boss_v01.stl` — Printed mount (PETG) (in cad/stl/)
- [ ] `containment_ring_v01.step` — burst containment (see section above) — **blocks Phase 2 spin-up**
- [ ] `vesc_flywheel.xml` — VESC Tool configuration export

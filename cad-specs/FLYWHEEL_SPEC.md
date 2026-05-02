# Flywheel (FESS) Specification — GyroDrone v0.1

> Kinetic energy storage and gyroscopic stabilization subsystem.

---

## Design Goals

| Goal | Target |
|---|---|
| Stored energy at 20,000 RPM | ≥ 15 Wh equivalent recoverable |
| Gyroscopic contribution | Measurable precession resistance |
| Mass | ≤ 120g (rotor + motor + bearing) |
| Diameter | ≤ 80mm (fits 110mm bay with clearance) |
| Height | ≤ 22mm total stack |

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

### Mass Estimate
```
Outer ring volume:  π × (40²-30²) × 15 = ~53,400 mm³  → ~144g
Center web volume:  π × 15² × 4        = ~2,827 mm³   → ~7.6g
Total estimated:    ~152g (pre-balance)
Post-balance target: ≤ 145g
```

### Moment of Inertia
```
Ring approximation (outer rim dominant):
I ≈ m_rim × r_avg²
  ≈ 0.144 × 0.035²
  ≈ 1.76 × 10⁻⁴ kg·m²

At 20,000 RPM (ω = 2094 rad/s):
L = I × ω = 1.76e-4 × 2094 = 0.369 kg·m²/s

Stored KE = ½ × I × ω²
          = ½ × 1.76e-4 × 2094²
          = ~386 J ≈ 0.107 Wh

Note: Real energy recovery efficiency via VESC ~70-80%
Effective recoverable: ~0.075-0.085 Wh per charge cycle
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

Spec: 6000-2RS Angular Contact
  ID: 10mm (motor shaft)
  OD: 26mm
  Width: 8mm
  Contact angle: 15° (handles combined radial + axial load)

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
  Max ERPM:       22,000 × pole_pairs
                  (RS2205 = 7 pole pairs → 154,000 ERPM)
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

- [ ] `flywheel_rotor_v01.step` — STEP for CNC machining
- [ ] `flywheel_rotor_v01.stl` — STL for reference/mockup
- [ ] `flywheel_mount_boss_v01.stl` — Printed mount (PETG)
- [ ] `vesc_flywheel.xml` — VESC Tool configuration export

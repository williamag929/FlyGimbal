# Gimbal Mount Specification — GyroDrone v0.1

> Thrust vectoring via servo-driven motor gimbal on 2 of 4 arms.

---

## Concept

Two of the four main motors are mounted on single-axis gimbals controlled by Savöx SH-0257MG digital servos. This allows **thrust vectoring** — tilting the motor/prop assembly to redirect thrust without changing RPM.

Combined with standard RPM differential on the other two fixed motors, this gives independent control over:
- Pitch authority (existing)
- Roll authority (existing)
- Yaw authority (enhanced — vectored thrust supplements torque reaction)
- Attitude recovery speed (improved — thrust vector acts faster than RPM ramp)

---

## Gimbal Geometry

```
Side view of one gimbaled motor arm:

    ┌──────────────────┐   ← CF arm (part of main frame ring)
    │   servo mount    │
    │  [SH-0257MG]     │
    │       │          │
    │    pivot pin     │   ← rotation axis (spanwise, M4 bolt)
    │       │          │
    │  [motor plate]   │   ← 30×30mm Al plate
    │  [EMAX 2807]     │
    └──────────────────┘

Rotation range: ±15° from vertical
Neutral: motor shaft vertical (same as fixed motors)
```

---

## Servo Selection Rationale

```
Savöx SH-0257MG
  Torque:    2.5 kg·cm @ 6V
  Speed:     0.07 sec/60°
  Weight:    9g
  Protocol:  PWM / analog

Torque requirement check:
  Motor + prop weight ≈ 90g = 0.09 kg
  Moment arm (motor CG to pivot) ≈ 15mm = 0.015m
  Static torque = 0.09 × 9.8 × 0.015 = 0.013 Nm = 0.13 kg·cm
  
  At max 15° deflection + gyroscopic coupling (2× safety):
  Required ≈ 0.3 kg·cm
  
  Savöx provides 2.5 kg·cm → 8× margin ✓
  Sufficient even with vibration and dynamic loading
```

---

## Bracket Dimensions (3D Print — PETG)

### Servo Mount Block
```
Material:   PETG (minimum), ASA preferred
Infill:     50% cubic
Walls:      4 perimeters

Dimensions:
  Width:    32mm (servo body + 1mm each side)
  Length:   45mm
  Height:   28mm
  
  Servo pocket: 23mm × 12mm × 28mm deep (SH-0257MG body)
  Servo flange slots: 3mm × 8mm elongated holes for adjustment
  Mount to arm: 2× M3 bolts through arm carbon (pre-drilled)
```

### Motor Plate (Aluminum 2mm)
```
  Size:     40mm × 40mm
  Motor pattern: 16mm × 16mm (M3)
  Pivot hole: 4mm center (M4 shoulder bolt)
  Servo horn attachment: 3mm offset from pivot, M2 screw
  
  Fabricate: Bend from 2mm Al sheet OR print PETG for prototype
```

### Pivot Pin
```
  M4 × 25mm shoulder bolt (smooth shank section = pivot)
  2× M4 nylon washers (reduce friction)
  M4 nyloc nut (loose enough to rotate freely)
```

---

## ArduCopter Configuration

```
SERVO outputs on H743:
  SERVO9_FUNCTION = 39  (Motor tilt front-right)
  SERVO10_FUNCTION = 40 (Motor tilt front-left)
  
  Or use custom Lua script for fine-grained mixing:
  -- tilt proportional to attitude error magnitude
  
Tilt angle mapping:
  PWM 1000 → -15° (tilt inward)
  PWM 1500 →   0° (neutral vertical)
  PWM 2000 → +15° (tilt outward)

Tilt authority blend:
  0-30% throttle: servo neutral (landing/takeoff safety)
  30-100% throttle: full servo authority enabled
```

---

## Which Arms Get Gimbals?

Install gimbaled motors at **front-left and front-right** positions (2 o'clock and 10 o'clock on disc):

```
        FRONT
    [G]       [G]    ← Gimbaled (vectored thrust)
         ( )
    [F]       [F]    ← Fixed (standard RPM control)
        REAR

G = Gimbaled motor (Savöx servo)
F = Fixed motor (standard mount)
```

Reason: Front motors dominate pitch authority. Vectoring pitch-forward motors amplifies pitch response — most useful for forward flight transition and momentum redirection in Dubins arcs.

---

## Files to Generate

- [ ] `gimbal_servo_mount_v01.stl` — PETG servo bracket
- [ ] `gimbal_motor_plate_v01.dxf` — 2mm Al motor plate (laser/CNC)
- [ ] `gimbal_assembly_v01.f3d` — Fusion 360 assembly with servo + motor

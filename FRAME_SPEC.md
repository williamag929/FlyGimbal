# Frame CAD Specification — GyroDrone Disc Frame v0.1

> Fusion 360 design parameters for the primary airframe.
> All dimensions in millimeters unless noted.

---

## Design Philosophy

Mass distribution follows the **flywheel principle**: maximum moment of inertia per unit weight requires mass concentrated at the maximum radius. The frame geometry enforces this structurally — the outer ring is the primary load-bearing element, not the center hub.

**Moment of inertia target:**
```
I = m·r²  (ring approximation)
For m=0.4kg ring at r=185mm:
I ≈ 0.4 × 0.185² = 0.01369 kg·m²

vs. equivalent mass quad at r=80mm:
I ≈ 0.4 × 0.080² = 0.00256 kg·m²

GyroDrone ring: ~5.3× more gyroscopic stability per kg
```

---

## Overall Dimensions

| Parameter | Value | Notes |
|---|---|---|
| Outer diameter | 400 mm | Motor tip-to-tip ~380mm |
| Inner hub diameter | 100 mm | Flywheel bay |
| Total frame height | 38 mm | Including motor mounts |
| Motor-to-motor (diag) | 283 mm | Effective wheelbase |
| Motor position | 185 mm from center | On ring perimeter |
| Frame weight target | ≤ 180 g | Carbon fiber 3mm |

---

## Layer Stack (top to bottom)

```
┌─────────────────────────────────────────┐  ← Top plate (2mm CF)
│  [M1]    electronics bay    [M2]        │    GPS, FC, VTX mounts
├─────────────────────────────────────────┤
│         standoffs (20mm M3)             │
├─────────────────────────────────────────┤
│  [M3]    flywheel bay       [M4]        │  ← Bottom plate (3mm CF)
│         (center void 100mm)             │    Main structural layer
└─────────────────────────────────────────┘

Motor positions at 90° intervals on ring perimeter
```

---

## Bottom Plate — Primary Structural Layer (3mm CF)

### Outer Ring
- **Outer radius:** 200 mm
- **Inner cut radius:** 155 mm
- **Ring width:** 45 mm
- **Purpose:** Primary mass concentration zone + motor mount pads

### Motor Mount Pads
- 4× pads at 0°, 90°, 180°, 270°
- Pad size: 30mm × 30mm, protruding outward from ring
- Motor bolt pattern: 16mm × 16mm (M3 screws)
- Motor center at exactly 185mm from frame center
- **Optional:** 2 pads on gimbal-mount (see GIMBAL_SPEC.md)

### Center Hub
- **Flywheel bay cutout:** 110mm diameter circle (center)
- **4× M3 standoff holes:** at 60mm radius, 90° intervals
- **4× wire routing slots:** 5mm × 20mm at 45° between standoff holes

### Arm Spokes
- 4× structural spokes connecting hub to ring
- Width: 15mm
- Taper: 18mm at hub → 12mm at ring junction
- Oriented at 45° offset from motor positions (X-pattern spokes, + pattern motors)
- **Reason:** Spokes at 45° decouple vibration paths from motor axes

### Cutouts for Weight Reduction
- 8× elliptical cutouts in ring between spokes and motors
- Ellipse: 40mm × 25mm
- Maintain minimum 12mm web between any cutout and structural edge

---

## Top Plate — Electronics Tray (2mm CF)

- Same outer profile as bottom plate
- **No flywheel cutout** — solid center for FC/ESC mounting
- FC mount: 30.5mm × 30.5mm standard pattern (center)
- ESC stack mount: same 30.5mm pattern, offset 5mm below FC
- Companion computer mount: 58mm × 23mm (Raspberry Pi Zero / Orange Pi Zero)
  - Position: 70mm from center, between 2 motor spokes
- 3× M2.5 rubber grommet holes for IMU isolation mount

---

## Flywheel Bay (center, bottom plate void)

- Clear cylinder: 110mm diameter × 25mm height
- Flywheel rotor OD: 80mm (10mm clearance each side)
- Motor mount boss below bottom plate: see FLYWHEEL_SPEC.md
- 4× M3 retention bolts at 55mm radius

---

## Material & Fabrication

### Recommended: Carbon Fiber Sheet (CNC cut)
```
Bottom plate: 3mm UD carbon fiber, 400×400mm sheet
Top plate:    2mm UD carbon fiber, 400×400mm sheet
Supplier:     PCBWay (custom CNC service)
              SendCutSend (US-based, fast turnaround)
              DragonPlate (higher quality CF)
Est. cost:    $45–65 for both plates
Turnaround:   7–14 days PCBWay, 3–5 days SendCutSend
```

### Alternative: FDM 3D Print (for prototyping)
```
Material:   ASA (UV resistant, low warp) or PETG
Infill:     40% gyroid pattern (isotropic strength)
Perimeters: 4 walls minimum
Layer:      0.2mm
Note:       Add 15g carbon fiber rods (4mm OD) in spoke channels
            for rigidity — print grooves for them in spoke geometry
```

---

## Fusion 360 Modeling Order

Follow this sequence to avoid constraint conflicts:

```
1. Create base sketch — circles at 200mm, 155mm, 110mm, 60mm radii
2. Define motor center points at 185mm, 0/90/180/270°
3. Draw motor pads (30×30mm) at each point
4. Draw spokes at 45/135/225/315° — loft from hub to ring
5. Add ring geometry — extrude 3mm
6. Cut flywheel void — 110mm circle through full depth
7. Cut arm slots, wire routing slots
8. Add elliptical lightening cutouts
9. Fillet all internal corners (R3mm minimum — CF delamination prevention)
10. Mirror/pattern to verify symmetry — CG must be at geometric center ±1mm
11. Export DXF for CNC — separate layers: cuts, drills, engraves
```

---

## Center of Gravity Targets

| Axis | Target | Max deviation |
|---|---|---|
| X (lateral) | 0 mm | ±3 mm |
| Y (longitudinal) | 0 mm | ±3 mm |
| Z (vertical) | 18 mm from bottom plate | ±4 mm |

**Z-axis CG:** Flywheel mass below CG raises stability — keep heavy components (battery, flywheel motor) at or below midplane.

---

## Standoffs & Hardware

```
Hub-to-tray standoffs:  M3 × 20mm aluminum (x4)
Motor bolts:            M3 × 8mm stainless (x16)
FC/ESC stack:           M3 × 6mm nylon + nylon nuts (x4, isolation)
Flywheel retention:     M3 × 12mm stainless (x4)
Landing legs (optional):3D printed TPU bumpers, press-fit on ring bottom
```

---

## Vibration Isolation Strategy

Critical for IMU accuracy and flywheel bearing life:

```
Level 1 — Motor isolation:
  Neoprene washers (1.5mm) between motor base and carbon pad

Level 2 — FC/ESC isolation:
  Standard M3 rubber grommets (FC stack standard)

Level 3 — IMU isolation:
  Separate IMU board on 3× M2.5 rubber standoffs
  Mounted away from motor axes (at 45° spoke intersection)

Level 4 — Flywheel bearing:
  Angular contact bearings (not radial) — see FLYWHEEL_SPEC.md
```

---

## Files to Generate

- [ ] `frame_bottom_v01.dxf` — CNC cut file, bottom plate
- [ ] `frame_top_v01.dxf` — CNC cut file, top plate
- [ ] `frame_assembly_v01.f3d` — Fusion 360 full assembly
- [ ] `motor_mount_v01.stl` — Optional printed motor adapter
- [ ] `landing_leg_v01.stl` — TPU landing bumpers (x4)

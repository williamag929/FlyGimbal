# Build Guide — GyroDrone Phase 1

> Step-by-step assembly for the disc frame + basic flight.
> Assumes engineer-level electronics experience.

---

## Tools Required

- Soldering iron (fine tip, 350°C)
- M2/M3 hex drivers (ball-end preferred for CF)
- Digital calipers
- Multimeter
- Threadlocker (Loctite 243)
- Heat gun or lighter (heat shrink)
- Laptop with Betaflight Configurator + Mission Planner installed
- USB-C cable
- 3–4mm CF drill bit (carbide, NOT HSS — CF destroys steel bits fast)

---

## Step 1 — Inspect Frame Plates

When CF plates arrive from PCBWay/SendCutSend:

1. Verify all dimensions with calipers — critical: motor mount holes must be at exactly 185mm from center
2. Check for delamination at edges — run finger along all cut edges
3. Sand all cut edges with 220-grit (CF edge dust is sharp and slightly hazardous — wear mask)
4. Test fit motor mounts — bolt pattern should align without stress

> ⚠️ Carbon fiber dust is a lung irritant. Sand/drill only with N95 mask and outdoors or with dust extraction.

---

## Step 2 — Drill and Tap Motor Mount Holes

CF plates typically arrive with holes. Verify:

1. Motor mount: 4× M3 holes per position, 16mm × 16mm pattern
2. FC/ESC stack: 30.5mm × 30.5mm, center of top plate
3. Standoff holes: M3, at 60mm radius on bottom plate

If holes need enlarging: use carbide bit at low speed, high pressure. CF doesn't drill like metal — let the bit cut, don't force it.

Do NOT tap CF threads — use M3 nyloc nuts on the back side, or press-in threaded inserts (M3 brass heat inserts work well with CF via CA glue, not heat).

---

## Step 3 — Install Standoffs

Bottom plate:
1. Insert M3 × 20mm aluminum standoffs through bottom plate holes
2. Secure with M3 nyloc nuts on the underside — no Loctite needed (nyloc sufficient)
3. Check standoffs are perpendicular to plate surface (use square)

---

## Step 4 — Solder ESC Stack

4-in-1 ESC stack (Tekko32 35A):

1. Pre-tin all pads before connecting anything
2. Main power leads: 16AWG, short as possible (<80mm)
3. Solder XT60 female connector to battery input pads
4. Motor phase wires: 20AWG, route through frame arm channels
5. Add capacitor (1000µF 35V electrolytic) across battery pads — reduces voltage spikes
6. Check: no solder bridges, no cold joints

**Motor direction wiring:**
Standard quad layout — verify with ArduCopter motor diagram for your frame type.
Incorrect direction fixed in software (BLHELI_32 direction reversal) — don't re-solder.

---

## Step 5 — Mount FC

Matek H743-SLIM on top plate:

1. Install M3 rubber grommets in FC mount holes
2. FC sits on grommets (vibration isolation — critical)
3. FC orientation: arrow pointing FORWARD (to front of disc)
4. Connect ESC stack to FC:
   - UART for DSHOT telemetry
   - 4× signal wires (DSHOT600 to ESC inputs)
   - 5V BEC from ESC to FC power input
5. Confirm FC is NOT touching any carbon fiber directly (shorts risk)

---

## Step 6 — Install Motors

At each of the 4 motor mount positions:

1. Place 1.5mm neoprene washer between motor base and CF pad
2. Insert motor, align bolt holes
3. Apply small drop Loctite 243 to M3 motor bolts
4. Torque to 0.5 N·m (snug, not gorilla-tight — CF strips)
5. Route motor phase wires through nearest slot in ring

**Check:** Spin each motor by hand after mounting — should spin freely with no binding or grinding. Any roughness = bearing issue, return the motor.

---

## Step 7 — Install RC Receiver

ExpressLRS EP1 receiver:

1. Bind receiver to transmitter first (bench, before installing)
2. Mount with double-sided tape on top plate, antenna oriented vertically
3. Connect: UART2 on H743 (TX2/RX2 pads)
4. In ArduCopter: SERIAL2_PROTOCOL = 23 (CRSF/ELRS)

---

## Step 8 — Flash ArduCopter

1. Download ArduCopter 4.5+ for MatekH743
2. Flash via Mission Planner: Initial Setup → Install Firmware → Load custom firmware
3. After flash, DO NOT set any params yet — let it boot clean

---

## Step 9 — Initial Configuration (Mission Planner)

```
Frame setup:
  FRAME_CLASS = 1 (Quad)
  FRAME_TYPE  = 1 (X)

Motor test (props OFF):
  Mission Planner → Optional Hardware → Motor Test
  Verify: A=front-right, B=rear-right, C=rear-left, D=front-left
  Correct direction in BLHeli_32 Configurator if needed

Accelerometer calibration:
  Initial Setup → Mandatory Hardware → Accel Calibration
  Follow 6-position sequence

Compass calibration:
  Initial Setup → Mandatory Hardware → Compass
  Rotate drone in all axes until complete

RC calibration:
  Radio Calibration → move all sticks to extremes

Flight modes:
  Ch5: Stabilize / AltHold / Loiter
```

---

## Step 10 — Pre-flight Checks

Before first flight, verify:

- [ ] All motor bolts Loctited and torqued
- [ ] Props installed correct direction (check blade pitch angle)
- [ ] Props tight on motor shafts (M5 bolt + washer)
- [ ] Battery lead polarity verified with multimeter BEFORE connecting battery
- [ ] No exposed wire near props arc
- [ ] FC armed/disarmed LED behavior correct
- [ ] Throttle failsafe set (loss of signal → disarm or land)
- [ ] Geofence set to 30m radius for first test

---

## Step 11 — First Hover (Tethered Recommended)

1. Outdoor open area, calm wind
2. Tie 4 light tethers (~2m) at motor arm tips to ground stakes
3. Arm and throttle up slowly to hover point
4. Observe: any oscillation? Any unusual vibration?
5. If oscillating: reduce P gains (Roll/Pitch P by 20%)
6. Hover 30 seconds, disarm, inspect: any loose screws? Motor heat?
7. Check ArduCopter logs for vibration levels (should be <15 m/s² noise)

---

## Phase 1 Complete When:

- [ ] Stable 5-minute hover
- [ ] Accel noise <15 m/s² in logs  
- [ ] No heating issues (motors <60°C after 5min)
- [ ] Control response feels normal in Stabilize mode
- [ ] Ready to proceed to Phase 2 (flywheel installation)

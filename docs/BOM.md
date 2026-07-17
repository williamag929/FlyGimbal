# Bill of Materials — GyroDrone v0.1

> All prices in USD. Sourced May 2025. Prices subject to change.

---

## Phase 1 — Frame + Basic Flight (~$200)

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 1 | Frame — bottom plate (3mm CF) | Custom CNC | 1 | 35 | 35 | PCBWay / SendCutSend |
| 2 | Frame — top plate (2mm CF) | Custom CNC | 1 | 25 | 25 | PCBWay / SendCutSend |
| 3 | Main motors | EMAX ECO II 2807 1300KV | 4 | 15 | 60 | GetFPV / Amazon |
| 4 | ESC 4-in-1 stack | Tekko32 F4 35A | 1 | 42 | 42 | GetFPV |
| 5 | Flight controller | Matek H743-SLIM | 1 | 60 | 60 | mateksys.com |
| 6 | Propellers | HQProp 9×4.5 3-blade | 4 pairs | 3 | 12 | HQProp |
| 7 | Battery (main) | CNHL 4S 3000mAh 100C | 1 | 30 | 30 | Amazon |
| 8 | RC receiver | ExpressLRS EP1 (2.4GHz) | 1 | 12 | 12 | Airbot / Banggood |
| 9 | Standoffs M3×20mm (Al) | Generic | 8 | — | 4 | Amazon |
| 10 | Hardware kit (screws, nuts) | M2/M3 assorted | 1 set | 8 | 8 | Amazon |
| **Phase 1 Total** | | | | | **~$288** | |

---

## Phase 2 — Flywheel + Gimbal (~$130)

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 11 | Flywheel rotor | Custom Al 6061 CNC | 1 | 30 | 30 | PCBWay CNC |
| 12 | Flywheel motor | Emax RS2205 2300KV | 1 | 15 | 15 | GetFPV |
| 13 | Flywheel ESC | VESC 4.12 | 1 | 40 | 40 | VESC Project / Flipsky |
| 14 | Bearings (deep groove, C3) | SKF 6000-2RS C3 — 10×26×8mm, 20g each | 2 | 10 | 20 | Amazon / SKF distributor |
| 15 | Flywheel battery | 2S 1000mAh LiPo | 1 | 12 | 12 | Amazon |
| 16 | Gimbal servos | Savöx SH-0257MG | 2 | 18 | 36 | Servo City / Amazon |
| 17 | Gimbal bracket | Custom PETG print | 2 | — | 4 (filament) | Local print |
| 18 | Flywheel mount boss | Custom PETG print | 1 | — | 2 (filament) | Local print |
| **Phase 2 Total** | | | | | **~$159** | |

---

## Phase 2a — Full Prototype, All-at-Once (~$447)

> **Alternative to Phases 1 + 2 combined.** Order everything below in a single pass and build the complete gyroscopic prototype without waiting for a Phase 1 flight-test milestone. Same total cost — benefit is fewer shipping runs and no component trickle-in delays.
>
> **No true duplicates exist between Phases 1 and 2.** The two ESCs serve different motors (Tekko32 → quad, VESC → flywheel). The two batteries are on different voltage rails (4S → main motors, 2S → flywheel VESC) and cannot be merged without a redesign. Hardware kit (item 10) covers both frame and gimbal assembly.

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 1 | Frame — bottom plate (3mm CF) | Custom CNC | 1 | 35 | 35 | PCBWay / SendCutSend |
| 2 | Frame — top plate (2mm CF) | Custom CNC | 1 | 25 | 25 | PCBWay / SendCutSend |
| 3 | Main motors | EMAX ECO II 2807 1300KV | 4 | 15 | 60 | GetFPV / Amazon |
| 4 | ESC 4-in-1 stack (quad) | Tekko32 F4 35A | 1 | 42 | 42 | GetFPV |
| 5 | Flight controller | Matek H743-SLIM | 1 | 60 | 60 | mateksys.com |
| 6 | Propellers | HQProp 9×4.5 3-blade | 4 pairs | 3 | 12 | HQProp |
| 7 | Flight battery | CNHL 4S 3000mAh 100C | 1 | 30 | 30 | Amazon |
| 8 | RC receiver | ExpressLRS EP1 (2.4GHz) | 1 | 12 | 12 | Airbot / Banggood |
| 9 | Standoffs M3×20mm (Al) | Generic | 8 | — | 4 | Amazon |
| 10 | Hardware kit (screws, nuts) | M2/M3 assorted — covers frame + gimbal | 1 set | 8 | 8 | Amazon |
| 11 | Flywheel rotor | Custom Al 6061 CNC | 1 | 30 | 30 | PCBWay CNC |
| 12 | Flywheel motor | Emax RS2205 2300KV | 1 | 15 | 15 | GetFPV |
| 13 | Flywheel ESC (VESC) | VESC 4.12 | 1 | 40 | 40 | VESC Project / Flipsky |
| 14 | Bearings (deep groove, C3) | SKF 6000-2RS C3 — 10×26×8mm, 20g each | 2 | 10 | 20 | Amazon / SKF distributor |
| 15 | Flywheel battery | 2S 1000mAh LiPo | 1 | 12 | 12 | Amazon |
| 16 | Gimbal servos | Savöx SH-0257MG | 2 | 18 | 36 | Servo City / Amazon |
| 17 | Gimbal bracket | Custom PETG print | 2 | — | 4 (filament) | Local print |
| 18 | Flywheel mount boss | Custom PETG print | 1 | — | 2 (filament) | Local print |
| **Phase 2a Total** | | | | | **~$447** | |

---

## Phase 3 — Companion Computer + Sensing (~$55)

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 19 | Companion computer | Orange Pi Zero 3 (1GB) | 1 | 20 | 20 | Orange Pi official |
| 20 | External IMU | ICM-42688-P breakout | 1 | 15 | 15 | Adafruit / SparkFun |
| 21 | UART cable (FC↔Pi) | JST-GH 4-pin | 2 | 3 | 6 | Amazon |
| 22 | MicroSD (OS) | SanDisk 32GB A1 | 1 | 8 | 8 | Amazon |
| 23 | Rubber grommets M2.5 | IMU isolation | 6 | — | 3 | Amazon |
| **Phase 3 Total** | | | | | **~$52** | |

---

## Phase 4A — Terrain Following / Precision Landing (~$26)

> Single downward-facing rangefinder. Enables terrain following, altitude hold independent of GPS, and precision landing. ArduPilot native — set `RNGFND1_TYPE=20`, `RNGFND1_ORIENT=25` (down).

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 24 | Downward rangefinder | Benewake TFmini-S | 1 | 25 | 25 | Amazon / Benewake |
| 25 | Sensor mount | Custom PETG print (downward bracket) | 1 | — | 1 (filament) | Local print |
| **Phase 4A Total** | | | | | **~$26** | |

---

## Phase 4B — Echolocation Array / Obstacle Avoidance (~$98)

> Five TF-Luna sensors arranged radially (front, rear, left, right, down) — the drone maps its surroundings in 360°, like whale echolocation. Requires the Orange Pi companion (Phase 3) or direct I2C to FC via multiplexer. ArduPilot `PRX_TYPE=4` (proximity) enables automatic obstacle avoidance in LOITER and AUTO modes.

| # | Component | Model | Qty | Unit $ | Total $ | Source |
|---|---|---|---|---|---|---|
| 26 | Proximity rangefinders | Benewake TF-Luna (8m, I2C) | 5 | 18 | 90 | Amazon / Benewake |
| 27 | I2C multiplexer | TCA9548A breakout | 1 | 5 | 5 | Adafruit / Amazon |
| 28 | Radial sensor mounts | Custom PETG print (×5 brackets) | 1 set | — | 3 (filament) | Local print |
| **Phase 4B Total** | | | | | **~$98** | |

> **Note:** Phase 4B replaces Phase 4A's downward sensor — the TF-Luna pointed down covers terrain following too. Don't buy both; go 4A first to validate ArduPilot rangefinder config, then upgrade to 4B.

---

## Miscellaneous / Consumables

| Item | Est. Cost |
|---|---|
| Heat shrink assorted | $5 |
| 16AWG / 20AWG wire (1m each) | $6 |
| XT60 connectors (2 pairs) | $4 |
| JST-PH connectors assorted | $4 |
| Loctite 243 (threadlocker) | $8 |
| CA glue + accelerator | $6 |
| Kapton tape | $3 |
| Cable ties 2.5mm | $3 |
| **Misc Total** | **~$39** |

---

## Grand Total by Phase

### Path A — Incremental (Phases 1 → 2 → 3 → 4)

| Phase | Component Scope | Cost |
|---|---|---|
| Phase 1 | Frame + basic flight | ~$288 |
| Phase 2 | Flywheel + gimbal (add-on) | ~$159 |
| Phase 3 | Companion + IMU | ~$52 |
| Phase 4A | Terrain following (single sonar) | ~$26 |
| Phase 4B | Echolocation array (upgrade) | ~$98 |
| Misc | Consumables | ~$39 |
| **GRAND TOTAL (4A only)** | | **~$662** |
| **GRAND TOTAL (full 4B)** | | **~$736** |

### Path B — Prototype First (Phase 2a → Phase 3 → 4)

| Phase | Component Scope | Cost |
|---|---|---|
| Phase 2a | Full prototype all-at-once | ~$447 |
| Phase 3 | Companion + IMU | ~$52 |
| Phase 4A | Terrain following (single sonar) | ~$26 |
| Phase 4B | Echolocation array (upgrade) | ~$98 |
| Misc | Consumables | ~$39 |
| **GRAND TOTAL (4A only)** | | **~$662** |
| **GRAND TOTAL (full 4B)** | | **~$736** |

> Same total cost either path through Phase 3. Phase 2a trades incremental validation for faster assembly. Phase 4B replaces 4A — don't stack both.

> ⚠️ Slightly over the $500 target. Cost reduction options:
> - Use AliExpress for motors (-$20): EMAX ECO II available ~$11/unit
> - PCBWay for CF frame vs SendCutSend (-$15)
> - Skip Phase 2 gimbal servos for initial hover validation (-$36, re-add before flywheel test)
> - **Adjusted Phase 1 only: ~$270** ← lowest-risk start

---

## Supplier Reference

| Supplier | Best For | Shipping |
|---|---|---|
| GetFPV.com | Motors, ESCs, FC | US, 2–5 days |
| mateksys.com | Matek FC direct | Ships from HK, 10–15 days |
| PCBWay.com | CNC + CF plates | 10–15 days |
| SendCutSend.com | CF/Al sheet cutting | US, 3–5 days |
| Amazon | Bearings, hardware, misc | Prime 1–2 days |
| Flipsky.net | VESC variants | 7–14 days |
| HQProp.com | Propellers | 7–10 days |
| Orange Pi (official) | Orange Pi Zero 3 | 2–3 weeks |

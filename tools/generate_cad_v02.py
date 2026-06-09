"""GyroDrone v02 CAD generator (CadQuery).

Generates the v02 lightening-pass frame plates, the burst-containment cup
(blocks Phase 2 spin-up), and the optional heavy rotor. Dimensions live here
as the single parametric source; exported STL/STEP/DXF are build artifacts.

    .venv/Scripts/python tools/generate_cad_v02.py

Outputs:
    cad/stl/<part>.stl          cad/stl/step/<part>.step
    cad/dxf/<plate>.dxf         (CNC cut profiles, frame plates only)

v02 design changes vs v01 (from the 2026-06-09 STL audit):
  frame_bottom: outer ring narrowed 45->14 mm band (R186-R200), hub annulus
                R55-R78, 4 spokes 14 mm @ 45 deg. ~165 g vs ~255 g as-built.
  frame_top:    full-diameter plate replaced by R80 electronics tray on the
                R60 standoffs, 8x 20 mm lightening holes. ~55 g vs ~201 g.
  containment:  NEW one-piece cup (ring + integral floor) instead of the
                ring + bolted cover in FLYWHEEL_SPEC — fewer parts, no
                fastener in the fragment path. Ears bolt to the bottom
                plate at R62 (shared with the flywheel boss).
  rotor v02:    optional heavy rotor, rim widened 10->13.5 mm and raised
                15->19.4 mm to hit I ~= 1.76e-4 kg m^2 (the original
                analytic spec value). v01 (I=1.16e-4) stays the default.

NOTE: the flywheel-boss bolt circle moves 55 -> 62 mm (R55 sat exactly on
the bay cutout edge — unbuildable). flywheel_boss_v01 needs a matching
flange update in Fusion before the v02 bottom plate is cut.
"""
from pathlib import Path
import math

import cadquery as cq
from cadquery import exporters

ROOT = Path(__file__).resolve().parent.parent
STL_DIR = ROOT / "cad" / "stl"
STEP_DIR = ROOT / "cad" / "stl" / "step"
DXF_DIR = ROOT / "cad" / "dxf"

RHO = {"cf": 1.6e-3, "al6061": 2.70e-3}  # g/mm^3

# ── shared frame parameters (mm) ─────────────────────────────────────────────
R_OUTER = 200.0          # frame outer radius
R_RING_IN = 186.0        # v02: ring band inner radius (v01: 155)
R_HUB_OUT = 78.0
R_BAY = 55.0             # flywheel bay cutout (110 mm dia)
R_MOTOR = 185.0          # motor centers
R_STANDOFF = 60.0        # M3 standoffs, at motor angles
R_BOSS = 62.0            # flywheel boss + containment ears, at spoke angles
SPOKE_W = 14.0
T_BOTTOM = 3.0
T_TOP = 2.0
HOLE_M3 = 3.2
HOLE_M25 = 2.7
MOTOR_ANGLES = (0, 90, 180, 270)
SPOKE_ANGLES = (45, 135, 225, 315)


def pol(r, deg):
    a = math.radians(deg)
    return (r * math.cos(a), r * math.sin(a))


def cyl(r, h, x=0.0, y=0.0, z=0.0):
    return (cq.Workplane("XY", origin=(x, y, z)).circle(r).extrude(h))


def holes(solid, dia, t, points):
    cutter = cq.Workplane("XY")
    for (x, y) in points:
        cutter = cutter.moveTo(x, y).circle(dia / 2.0)
    return solid.cut(cutter.extrude(t).translate((0, 0, -0.5)) if False
                     else cutter.extrude(t))


def motor_bolt_points():
    """16x16 mm M3 pattern at each motor center."""
    pts = []
    for ang in MOTOR_ANGLES:
        cx, cy = pol(R_MOTOR, ang)
        for dx in (-8, 8):
            for dy in (-8, 8):
                pts.append((cx + dx, cy + dy))
    return pts


# ── frame_bottom_v02 (3 mm CF) ───────────────────────────────────────────────

def frame_bottom():
    t = T_BOTTOM
    ring = cyl(R_OUTER, t).cut(cyl(R_RING_IN, t))
    hub = cyl(R_HUB_OUT, t).cut(cyl(R_BAY, t))
    plate = ring.union(hub)
    for ang in SPOKE_ANGLES:                       # spokes bridge hub -> ring
        spoke = (cq.Workplane("XY")
                 .box(125, SPOKE_W, t, centered=(True, True, False))
                 .translate((132.5, 0, 0))         # spans R70..R195
                 .rotate((0, 0, 0), (0, 0, 1), ang))
        plate = plate.union(spoke)
    for ang in MOTOR_ANGLES:                       # motor pads 30x30 @ R185
        pad = (cq.Workplane("XY")
               .box(30, 30, t, centered=(True, True, False))
               .translate((R_MOTOR, 0, 0))
               .rotate((0, 0, 0), (0, 0, 1), ang))
        plate = plate.union(pad)

    plate = holes(plate, HOLE_M3, t, motor_bolt_points())
    plate = holes(plate, HOLE_M3, t, [pol(R_STANDOFF, a) for a in MOTOR_ANGLES])
    plate = holes(plate, HOLE_M3, t, [pol(R_BOSS, a) for a in SPOKE_ANGLES])

    # wire routing slots 16x5 radial, between standoff and boss angles
    for ang in (22.5, 112.5, 202.5, 292.5):
        x, y = pol(66.5, ang)
        slot = (cq.Workplane("XY", origin=(x, y, 0))
                .slot2D(16, 5, ang).extrude(t))
        plate = plate.cut(slot)
    return plate


# ── frame_top_v02 (2 mm CF, R80 electronics tray) ───────────────────────────

def frame_top():
    t = T_TOP
    plate = cyl(80.0, t)
    # FC stack 30.5 x 30.5 M3
    plate = holes(plate, HOLE_M3, t,
                  [(sx * 15.25, sy * 15.25) for sx in (-1, 1) for sy in (-1, 1)])
    # companion computer 58 x 23 M2.5 (Pi Zero / OPi Zero), +Y side
    plate = holes(plate, HOLE_M25, t,
                  [(sx * 29.0, 55.0 + sy * 11.5) for sx in (-1, 1) for sy in (-1, 1)])
    # standoffs
    plate = holes(plate, HOLE_M3, t, [pol(R_STANDOFF, a) for a in MOTOR_ANGLES])
    # IMU isolation grommets 3x M2.5
    plate = holes(plate, HOLE_M25, t, [pol(38.0, a) for a in (210, 270, 330)])
    # lightening holes (skip the 45-135 deg sector: companion bay)
    plate = holes(plate, 20.0, t,
                  [pol(64.0, a) for a in (22.5, 157.5, 202.5, 225,
                                          247.5, 292.5, 315, 337.5)])
    return plate


# ── containment_cup_v01 (6061, one-piece burst containment) ─────────────────

CUP_ID = 86.0      # 3 mm radial clearance to 80 mm rotor
CUP_WALL = 3.0
CUP_H = 24.0       # interior depth 21.5 — clears v02 rotor (19.4) + 2 mm
CUP_FLOOR = 2.5
CUP_SHAFT_HOLE = 16.0

def containment_cup():
    r_in, r_out = CUP_ID / 2.0, CUP_ID / 2.0 + CUP_WALL
    cup = cyl(r_out, CUP_H)
    cup = cup.cut(cyl(r_in, CUP_H - CUP_FLOOR, z=CUP_FLOOR))    # bore, keep floor
    cup = cup.cut(cyl(CUP_SHAFT_HOLE / 2.0, CUP_FLOOR))         # wire/shaft hole
    for ang in SPOKE_ANGLES:                                    # mounting ears
        ear = (cq.Workplane("XY")
               .box(28, 12, 3.0, centered=(True, True, False))
               .translate((54.0, 0, CUP_H - 3.0))               # spans R40..R68
               .rotate((0, 0, 0), (0, 0, 1), ang))
        cup = cup.union(ear)
    ear_holes = cq.Workplane("XY")
    for ang in SPOKE_ANGLES:
        x, y = pol(R_BOSS, ang)
        ear_holes = ear_holes.moveTo(x, y).circle(HOLE_M3 / 2.0)
    cup = cup.cut(ear_holes.extrude(CUP_H))
    return cup


# ── flywheel_rotor_v02 (6061, I target 1.76e-4 kg m^2) ──────────────────────

ROTOR_R = 40.0
ROTOR_H = 19.4
RIM_R_IN = 26.5
WEB_T = 4.0
BORE_R = 15.0

def rotor_v02():
    r = cyl(ROTOR_R, ROTOR_H)
    r = r.cut(cyl(RIM_R_IN, ROTOR_H - WEB_T, z=WEB_T))   # pocket above web
    r = r.cut(cyl(BORE_R, ROTOR_H))                      # motor bore
    return r


def rotor_v02_inertia():
    """Analytic check: Izz and mass of the v02 rotor."""
    rho = 2700.0  # kg/m^3
    def ann(r1, r2, h):       # annulus: (mass, Izz)
        m = rho * math.pi * (r2**2 - r1**2) * h
        return m, 0.5 * m * (r1**2 + r2**2)
    m_rim, i_rim = ann(RIM_R_IN / 1e3, ROTOR_R / 1e3, ROTOR_H / 1e3)
    m_web, i_web = ann(BORE_R / 1e3, RIM_R_IN / 1e3, WEB_T / 1e3)
    return m_rim + m_web, i_rim + i_web


# ── export ───────────────────────────────────────────────────────────────────

def export(name, solid, material, dxf=False):
    vol = solid.val().Volume()                      # mm^3
    mass = vol * RHO[material]
    STL_DIR.mkdir(parents=True, exist_ok=True)
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    exporters.export(solid, str(STL_DIR / f"{name}.stl"),
                     tolerance=0.05, angularTolerance=0.2)
    exporters.export(solid, str(STEP_DIR / f"{name}.step"))
    if dxf:
        DXF_DIR.mkdir(parents=True, exist_ok=True)
        exporters.export(solid.section(), str(DXF_DIR / f"{name}.dxf"))
    print(f"  {name:24s} {vol/1000.0:7.1f} cm^3  {mass:6.1f} g  ({material})"
          f"{'  +DXF' if dxf else ''}")
    return mass


if __name__ == "__main__":
    print("GyroDrone v02 CAD generation:")
    m_bot = export("frame_bottom_v02", frame_bottom(), "cf", dxf=True)
    m_top = export("frame_top_v02", frame_top(), "cf", dxf=True)
    m_cup = export("containment_cup_v01", containment_cup(), "al6061")
    m_rot = export("flywheel_rotor_v02", rotor_v02(), "al6061")

    m_an, izz = rotor_v02_inertia()
    print(f"\n  plates total: {m_bot+m_top:.0f} g (v01 as-built: ~456 g)")
    print(f"  rotor v02 analytic: {m_an*1000:.0f} g, Izz = {izz:.3e} kg m^2 "
          f"(target 1.76e-4)")
    print(f"  KE at 20k RPM: {0.5*izz*(20000*2*math.pi/60)**2:.0f} J")

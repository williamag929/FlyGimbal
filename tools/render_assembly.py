"""Render the GyroDrone v02 prototype assembly from the released STLs.

Painter's-algorithm shaded render (no extra deps beyond numpy/matplotlib).
Motors, props, and standoffs are simple generated cylinders for context —
they are not released geometry.

    .venv/Scripts/python tools/render_assembly.py   ->  cad/preview_assembly.png
"""
import struct
import math
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROOT = Path(__file__).resolve().parent.parent
STL = ROOT / "cad" / "stl"


def load_stl(path):
    d = Path(path).read_bytes()
    n = struct.unpack_from("<I", d, 80)[0]
    out = np.empty((n, 3, 3), dtype=np.float64)
    off = 84
    for i in range(n):
        v = struct.unpack_from("<12f", d, off)
        out[i] = np.array(v[3:]).reshape(3, 3)
        off += 50
    return out


def cylinder(r, h, x=0.0, y=0.0, z=0.0, seg=24):
    """Closed cylinder as triangles, base center at (x,y,z)."""
    a = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    pts0 = np.stack([x + r * np.cos(a), y + r * np.sin(a), np.full(seg, z)], 1)
    pts1 = pts0 + [0, 0, h]
    tris = []
    for i in range(seg):
        j = (i + 1) % seg
        tris.append([pts0[i], pts0[j], pts1[j]])
        tris.append([pts0[i], pts1[j], pts1[i]])
        tris.append([[x, y, z], pts0[j], pts0[i]])           # bottom cap
        tris.append([[x, y, z + h], pts1[i], pts1[j]])       # top cap
    return np.array(tris)


def pol(r, deg):
    a = math.radians(deg)
    return r * math.cos(a), r * math.sin(a)


def assembly(explode=0.0):
    """Return list of (tris, base_color). explode = extra z separation."""
    e = explode
    parts = []
    grey_cf = (0.22, 0.24, 0.27)
    alu = (0.72, 0.74, 0.78)
    orange = (0.85, 0.45, 0.10)
    dark = (0.15, 0.15, 0.18)
    prop = (0.35, 0.55, 0.35)

    bot = load_stl(STL / "frame_bottom_v02.stl")
    top = load_stl(STL / "frame_top_v02.stl") + [0, 0, 23 + 2.0 * e]
    cup = load_stl(STL / "containment_cup_v01.stl") + [0, 0, -24 - 1.5 * e]
    rot_path = STL / "flywheel_rotor_v01.stl"          # user may shelve v01 files
    if not rot_path.exists():
        rot_path = STL / "v01" / "flywheel_rotor_v01.stl"
    rot = load_stl(rot_path) + [0, 0, -17 - 0.75 * e]

    parts += [(bot, grey_cf), (top, grey_cf), (cup, alu), (rot, orange)]

    for ang in (0, 90, 180, 270):
        x, y = pol(185, ang)
        parts.append((cylinder(14, 22, x, y, 3 + 0.5 * e), dark))          # motor
        parts.append((cylinder(63.5, 1.5, x, y, 25 + 1.5 * e), prop))      # prop disc
        sx, sy = pol(60, ang)
        parts.append((cylinder(2.5, 20, sx, sy, 3 + e), (0.5, 0.5, 0.55)))  # standoff
    return parts


def render(ax, parts, view=(1.0, 1.0, 0.55), title=""):
    v = np.array(view) / np.linalg.norm(view)
    # orthographic basis
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(up, v); right /= np.linalg.norm(right)
    up2 = np.cross(v, right)
    light = np.array([0.3, 0.5, 0.85]); light /= np.linalg.norm(light)

    polys, colors, depth = [], [], []
    for tris, base in parts:
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        nl = np.linalg.norm(n, axis=1); keep = nl > 1e-12
        tris, n = tris[keep], (n[keep].T / nl[keep]).T
        face = n @ v
        vis = face > 0                      # backface cull (closed meshes)
        tris, n = tris[vis], n[vis]
        shade = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
        c = np.clip(np.outer(shade, base), 0, 1)
        polys.append(np.stack([tris @ right, tris @ up2], -1))
        colors.append(c)
        depth.append(tris.mean(1) @ v)
    polys = np.concatenate(polys); colors = np.concatenate(colors)
    depth = np.concatenate(depth)
    order = np.argsort(depth)               # far -> near
    ax.add_collection(PolyCollection(polys[order], facecolors=colors[order],
                                     linewidths=0))
    ax.autoscale_view()
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(title, fontsize=13)


if __name__ == "__main__":
    fig, axes = plt.subplots(1, 2, figsize=(17, 9))
    render(axes[0], assembly(0.0), title="GyroDrone v02 — assembled prototype")
    render(axes[1], assembly(30.0), title="exploded view")
    fig.text(0.5, 0.03,
             "CF plates (dark) · 6061 containment cup + rotor (silver/orange) · "
             "motors + 5\" props + standoffs are placeholders",
             ha="center", fontsize=10, color="0.4")
    plt.tight_layout()
    out = ROOT / "cad" / "preview_assembly.png"
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print(f"wrote {out}")

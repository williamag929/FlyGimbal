"""Quick STL geometry audit: bounding box, volume, inertia estimate."""
import struct, sys, math
from pathlib import Path

def read_binary_stl(path):
    data = Path(path).read_bytes()
    if len(data) < 84:
        return None
    n = struct.unpack_from("<I", data, 80)[0]
    if 84 + n * 50 != len(data):
        return None  # ascii or malformed
    tris = []
    off = 84
    for _ in range(n):
        vals = struct.unpack_from("<12f", data, off)
        tris.append(vals[3:])  # skip normal: 3 verts x 3
        off += 50
    return tris

def analyze(path):
    tris = read_binary_stl(path)
    if tris is None:
        return f"{Path(path).name}: not binary STL / unreadable"
    xs, ys, zs = [], [], []
    vol = 0.0
    izz = 0.0  # about z through origin, per-tet approximation
    for t in tris:
        v0, v1, v2 = t[0:3], t[3:6], t[6:9]
        for v in (v0, v1, v2):
            xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
        # signed tetra volume (origin)
        v = (v0[0]*(v1[1]*v2[2]-v1[2]*v2[1])
           - v0[1]*(v1[0]*v2[2]-v1[2]*v2[0])
           + v0[2]*(v1[0]*v2[1]-v1[1]*v2[0])) / 6.0
        vol += v
        # exact tetra Izz (vertex at origin):
        # integral(x^2+y^2) dV = V/10 * (sum_i q_i^2 + sum_{i<j} q_i q_j), q in {x,y}
        sx = v0[0]*v0[0] + v1[0]*v1[0] + v2[0]*v2[0] \
           + v0[0]*v1[0] + v0[0]*v2[0] + v1[0]*v2[0]
        sy = v0[1]*v0[1] + v1[1]*v1[1] + v2[1]*v2[1] \
           + v0[1]*v1[1] + v0[1]*v2[1] + v1[1]*v2[1]
        izz += v * (sx + sy) / 10.0
    dx = max(xs)-min(xs); dy = max(ys)-min(ys); dz = max(zs)-min(zs)
    return (f"{Path(path).name:32s} tris={len(tris):6d}  "
            f"bbox: {dx:7.1f} x {dy:7.1f} x {dz:6.1f} mm  "
            f"vol: {abs(vol)/1000.0:9.1f} cm^3  "
            f"Izz/rho: {abs(izz)/1e12:.3e} m^5")

if __name__ == "__main__":
    for p in sorted(Path(sys.argv[1]).glob("*.stl")):
        print(analyze(p))

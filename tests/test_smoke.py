"""Smoke tests for the FlyGimbal simulation and path planner.

No hardware, no SITL, no matplotlib required. Run with:
    pytest tests/ -v
"""

import math
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "simulation"))
sys.path.insert(0, os.path.join(ROOT, "src", "pathfinding"))

import gyrodrone_sim as sim  # noqa: E402
import dubins_momentum as planner  # noqa: E402


# ── Dubins sampler ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("q1", [
    (20.0, 0.0, math.pi / 2),
    (20.0, 20.0, math.pi),
    (-10.0, 5.0, -math.pi / 2),
])
def test_dubins_sample_ends_at_goal(q1):
    pts = sim.dubins_sample((0.0, 0.0, 0.0), q1, rho=5.0, step=0.4)
    x, y, _ = pts[-1]
    assert math.hypot(x - q1[0], y - q1[1]) < 0.5


def test_dubins_sample_step_spacing():
    pts = sim.dubins_sample((0.0, 0.0, 0.0), (20.0, 20.0, math.pi), rho=5.0, step=0.4)
    gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    assert max(gaps) <= 0.4 * 1.01  # arc chords can round slightly over


# ── Momentum-aware planner ─────────────────────────────────────────────────

def test_turn_radius_tightens_with_flywheel_charge():
    fw = planner.FlywheelState()
    p = planner.MomentumDubinsPlanner(fw)
    fw.rpm = planner.FLYWHEEL_RPM_MIN
    r_low = p.effective_turn_radius()
    fw.rpm = planner.FLYWHEEL_RPM_MAX
    r_high = p.effective_turn_radius()
    assert r_high < r_low
    assert r_high == pytest.approx(p.min_turn_radius(), rel=0.05)


def test_plan_mission_produces_path():
    fw = planner.FlywheelState()
    fw.rpm = 18_000
    path = planner.MomentumDubinsPlanner(fw).plan_mission(sim.MISSIONS["circuit"])
    assert len(path) > 50


# ── Full physics mission ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
def circuit():
    m = sim.Mission(waypoints=sim.MISSIONS["circuit"], dt=0.02)
    m.run()
    return m


def test_circuit_holds_altitude(circuit):
    err = [abs(t.alt - circuit.alt) for t in circuit.tel]
    assert max(err) < 1.5


def test_circuit_recovers_energy(circuit):
    assert max(t.regen_w for t in circuit.tel) > 0


def test_circuit_attitude_stays_small(circuit):
    worst = max(max(abs(t.phi), abs(t.theta)) for t in circuit.tel)
    assert math.degrees(worst) < 25


def test_windy_noisy_mission_stays_stable():
    m = sim.Mission(waypoints=sim.MISSIONS["circuit"], dt=0.01, wind_dir=90.0,
                    wind_speed=8.0, gust_sigma=3.0, noise=True)
    m.run()
    err = [abs(t.alt - m.alt) for t in m.tel]
    assert sum(err) / len(err) < 1.5  # stays stable, not a precision test
    assert max(err) < 5.0

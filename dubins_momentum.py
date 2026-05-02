"""
GyroDrone — Momentum-Aware Dubins Path Planner
src/pathfinding/dubins_momentum.py

Extends standard Dubins path with flywheel state constraints.
Runs on companion computer (Orange Pi Zero 3) via MAVLink to ArduCopter.

Dependencies:
    pip install dubins pymavlink numpy

Usage:
    python dubins_momentum.py --connect /dev/ttyS1 --baud 115200
"""

import math
import time
import argparse
import numpy as np

try:
    import dubins
    from pymavlink import mavutil
except ImportError:
    print("Install: pip install dubins pymavlink numpy")
    raise


# ─── Constants ────────────────────────────────────────────────────────────────

FLYWHEEL_RPM_MAX    = 20_000   # RPM at full charge
FLYWHEEL_RPM_MIN    =  5_000   # Below this, no useful regen
DRONE_MASS_KG       =      1.2
G                   =      9.8
BANK_ANGLE_MAX_DEG  =     30.0 # Max tilt for arc turns
CRUISE_SPEED_MS     =      5.0 # m/s nominal


# ─── Flywheel State (read from VESC via UART) ─────────────────────────────────

class FlywheelState:
    """
    Reads flywheel RPM from VESC over UART.
    Falls back to simulated state if VESC not connected.
    """

    def __init__(self, port: str = "/dev/ttyS3", baud: int = 115200):
        self.rpm      = 0
        self.energy_j = 0.0
        self._sim     = True  # Switch to False when VESC is wired

        # Flywheel rotor moment of inertia (from FLYWHEEL_SPEC.md)
        self.I = 1.76e-4  # kg·m²

        if not self._sim:
            try:
                import serial
                self._ser = serial.Serial(port, baud, timeout=0.1)
            except Exception as e:
                print(f"[FlywheelState] UART open failed: {e} — using simulation")
                self._sim = True

    def update(self):
        """Poll VESC for current RPM."""
        if self._sim:
            # Simulate flywheel draining slowly for testing
            self.rpm = max(FLYWHEEL_RPM_MIN, self.rpm - 50)
            if self.rpm <= FLYWHEEL_RPM_MIN:
                self.rpm = FLYWHEEL_RPM_MAX  # Reset cycle in sim
        else:
            # TODO: implement VESC UART protocol read
            # VESC sends: RPM, current, duty, voltage
            pass

        omega = self.rpm * 2 * math.pi / 60
        self.energy_j = 0.5 * self.I * omega ** 2

    @property
    def charge_fraction(self) -> float:
        """0.0 (empty) to 1.0 (full)"""
        rpm_clamped = max(FLYWHEEL_RPM_MIN, min(FLYWHEEL_RPM_MAX, self.rpm))
        return (rpm_clamped - FLYWHEEL_RPM_MIN) / (FLYWHEEL_RPM_MAX - FLYWHEEL_RPM_MIN)

    def __repr__(self):
        return f"FlywheelState(rpm={self.rpm:.0f}, energy={self.energy_j:.1f}J, charge={self.charge_fraction:.0%})"


# ─── Momentum-Aware Path Planner ─────────────────────────────────────────────

class MomentumDubinsPlanner:
    """
    Plans Dubins paths between waypoints with turning radius
    dynamically adjusted based on flywheel energy state.

    Key insight:
        Tighter turns require more corrective effort from rotors.
        When flywheel has stored energy (high RPM), gyroscopic
        stabilization compensates — tighter turns are "cheaper".
        When flywheel is depleted, enforce gentler arcs.
    """

    def __init__(self, flywheel: FlywheelState):
        self.flywheel = flywheel

    def min_turn_radius(self, speed_ms: float = CRUISE_SPEED_MS) -> float:
        """
        Base minimum turn radius from physics:
            r_min = v² / (g × tan(bank_max))
        """
        bank_rad = math.radians(BANK_ANGLE_MAX_DEG)
        return speed_ms ** 2 / (G * math.tan(bank_rad))

    def effective_turn_radius(self, speed_ms: float = CRUISE_SPEED_MS) -> float:
        """
        Adjusted radius based on flywheel state.

        - Full flywheel (charge=1.0): can use min_turn_radius (tightest)
        - Empty flywheel (charge=0.0): enforce 2× min_turn_radius (gentlest)

        Linear interpolation between these extremes.
        """
        r_min = self.min_turn_radius(speed_ms)
        r_max = r_min * 2.0  # Conservative limit when flywheel empty

        charge = self.flywheel.charge_fraction
        # Invert: high charge → low (tight) radius
        radius = r_max - (r_max - r_min) * charge
        return radius

    def plan_segment(
        self,
        start: tuple,   # (x, y, heading_rad)
        end:   tuple,   # (x, y, heading_rad)
        speed_ms: float = CRUISE_SPEED_MS,
    ) -> list[tuple]:
        """
        Generate Dubins path from start to end configuration.

        Returns list of (x, y, heading_rad) waypoints along the arc.
        """
        self.flywheel.update()
        radius = self.effective_turn_radius(speed_ms)

        path = dubins.shortest_path(start, end, radius)
        configurations, _ = path.sample_many(step_size=0.5)

        print(
            f"[Planner] r={radius:.2f}m | flywheel={self.flywheel} "
            f"| path_type={path.path_type()} | length={path.path_length():.1f}m"
        )

        return configurations

    def plan_mission(
        self,
        waypoints: list[tuple],  # list of (x, y, heading_deg)
        speed_ms: float = CRUISE_SPEED_MS,
    ) -> list[tuple]:
        """
        Plan full multi-waypoint mission as connected Dubins segments.
        Heading in degrees, converted internally to radians.
        """
        all_configs = []

        for i in range(len(waypoints) - 1):
            wp_start = waypoints[i]
            wp_end   = waypoints[i + 1]

            start = (wp_start[0], wp_start[1], math.radians(wp_start[2]))
            end   = (wp_end[0],   wp_end[1],   math.radians(wp_end[2]))

            segment = self.plan_segment(start, end, speed_ms)
            all_configs.extend(segment)

        return all_configs


# ─── MAVLink Interface ────────────────────────────────────────────────────────

class ArduPilotInterface:
    """
    Sends planned path to ArduCopter via MAVLink.
    Requires SERIAL2 on H743 connected to companion UART.
    """

    def __init__(self, connection_string: str, baud: int = 115200):
        print(f"[MAVLink] Connecting to {connection_string} @ {baud}...")
        self.mav = mavutil.mavlink_connection(connection_string, baud=baud)
        self.mav.wait_heartbeat()
        print(f"[MAVLink] Heartbeat received from system {self.mav.target_system}")

    def upload_mission(self, configs: list[tuple], altitude_m: float = 10.0):
        """
        Upload Dubins path as MAVLink mission waypoints.
        configs: list of (x_local, y_local, heading_rad) in local frame
        """
        # Convert local NED to global lat/lon requires GPS origin
        # For now, send as SET_POSITION_TARGET_LOCAL_NED in GUIDED mode
        print(f"[MAVLink] Uploading {len(configs)} path points...")

        for i, (x, y, heading) in enumerate(configs):
            self.mav.mav.set_position_target_local_ned_send(
                time_boot_ms=int(time.time() * 1000) & 0xFFFFFFFF,
                target_system=self.mav.target_system,
                target_component=self.mav.target_component,
                coordinate_frame=mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                type_mask=0b0000_1111_1111_1000,  # position only
                x=x,
                y=y,
                z=-altitude_m,  # NED: negative = up
                vx=0, vy=0, vz=0,
                afx=0, afy=0, afz=0,
                yaw=heading,
                yaw_rate=0,
            )
            time.sleep(0.05)  # 20Hz send rate

        print("[MAVLink] Mission upload complete.")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GyroDrone Momentum Path Planner")
    parser.add_argument("--connect", default="udp:127.0.0.1:14550", help="MAVLink connection string")
    parser.add_argument("--baud",    default=115200, type=int)
    parser.add_argument("--sim",     action="store_true", help="Run in simulation mode (no hardware)")
    args = parser.parse_args()

    # Example 5-point circuit mission
    # Format: (x_meters, y_meters, heading_degrees)
    mission = [
        ( 0,   0,  0),
        (20,   0, 90),
        (20,  20, 180),
        ( 0,  20, 270),
        ( 0,   0,   0),
    ]

    flywheel = FlywheelState()
    flywheel.rpm = 18_000  # Simulate charged flywheel

    planner = MomentumDubinsPlanner(flywheel)
    path    = planner.plan_mission(mission)

    print(f"\n[Main] Total path points: {len(path)}")
    print(f"[Main] First 3 points: {path[:3]}")

    if not args.sim:
        mav = ArduPilotInterface(args.connect, args.baud)
        mav.upload_mission(path)
    else:
        print("[Main] Simulation mode — no MAVLink connection.")
        print("[Main] Path generated successfully. Connect hardware to fly.")


if __name__ == "__main__":
    main()

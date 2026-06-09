"""
FlyGimbal — Momentum Manager
src/momentum-manager/momentum_manager.py

Central coordinator between:
  - Flywheel state (VESC telemetry)
  - Flight controller (MAVLink)
  - Path planner (Dubins)
  - Energy budget decisions

Runs on companion computer (Orange Pi Zero 3).
Communicates with H743 via UART/MAVLink and VESC via UART.

Dependencies:
    pip install pymavlink numpy pyserial

Usage:
    python momentum_manager.py --fc /dev/ttyS1 --vesc /dev/ttyS3
    python momentum_manager.py --sim   # full simulation, no hardware
"""

import time
import math
import threading
import logging
import argparse
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import deque
from typing import Optional

try:
    from pymavlink import mavutil
except ImportError:
    mavutil = None

try:
    import serial
except ImportError:
    serial = None

import numpy as np

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("MomentumManager")


# ─── Constants ────────────────────────────────────────────────────────────────

FLYWHEEL_I          = 1.16e-4   # kg·m²  — as-built v01 rotor (118g, from STL)
FLYWHEEL_RPM_MAX    = 20_000    # RPM    — full charge
FLYWHEEL_RPM_MIN    =  5_000    # RPM    — min useful (below = no regen gain)
FLYWHEEL_RPM_IDLE   =  8_000    # RPM    — default hover setpoint
FLYWHEEL_RPM_BOOST  = 18_000    # RPM    — pre-maneuver charge target
REGEN_EFFICIENCY    =  0.72     # 72%    — VESC regen efficiency
DRONE_MASS_KG       =  1.2      # kg
G                   =  9.81     # m/s²
BANK_MAX_DEG        = 30.0      # degrees

# Energy thresholds (Joules)
KE_MAX = 0.5 * FLYWHEEL_I * (FLYWHEEL_RPM_MAX * 2*math.pi/60)**2   # ~254 J
KE_MIN = 0.5 * FLYWHEEL_I * (FLYWHEEL_RPM_MIN * 2*math.pi/60)**2   # ~16 J

# Telemetry ring buffer size
TELEM_BUFFER = 100


# ─── Data Structures ──────────────────────────────────────────────────────────

class FlywheelMode(Enum):
    IDLE      = auto()   # spinning at idle RPM, no active regen
    CHARGING  = auto()   # spinning up to target
    HOLDING   = auto()   # maintaining setpoint
    REGEN     = auto()   # capturing energy from descent/braking
    DISCHARGE = auto()   # releasing energy to assist maneuver
    FAULT     = auto()   # error state


@dataclass
class FlywheelTelemetry:
    rpm:          float = 0.0
    current_a:    float = 0.0
    voltage_v:    float = 0.0
    temp_c:       float = 0.0
    energy_j:     float = 0.0
    charge_pct:   float = 0.0
    mode:         FlywheelMode = FlywheelMode.IDLE
    timestamp:    float = field(default_factory=time.time)

    def update_energy(self):
        omega = self.rpm * 2 * math.pi / 60
        self.energy_j   = 0.5 * FLYWHEEL_I * omega**2
        rpm_clamped     = max(FLYWHEEL_RPM_MIN, min(FLYWHEEL_RPM_MAX, self.rpm))
        self.charge_pct = (rpm_clamped - FLYWHEEL_RPM_MIN) / (FLYWHEEL_RPM_MAX - FLYWHEEL_RPM_MIN) * 100


@dataclass
class FlightTelemetry:
    lat:            float = 0.0
    lon:            float = 0.0
    alt_m:          float = 0.0
    vx_ms:          float = 0.0    # velocity N (m/s)
    vy_ms:          float = 0.0    # velocity E (m/s)
    vz_ms:          float = 0.0    # velocity D (m/s, positive = down)
    roll_deg:       float = 0.0
    pitch_deg:      float = 0.0
    yaw_deg:        float = 0.0
    groundspeed_ms: float = 0.0
    armed:          bool  = False
    mode:           str   = "UNKNOWN"
    battery_pct:    float = 100.0
    battery_v:      float = 0.0
    timestamp:      float = field(default_factory=time.time)

    @property
    def descending(self) -> bool:
        return self.vz_ms > 0.3   # NED: positive vz = descending

    @property
    def ascending(self) -> bool:
        return self.vz_ms < -0.3

    @property
    def kinetic_energy_j(self) -> float:
        speed = math.sqrt(self.vx_ms**2 + self.vy_ms**2 + self.vz_ms**2)
        return 0.5 * DRONE_MASS_KG * speed**2


@dataclass
class EnergyBudget:
    """Current energy accounting across all stores."""
    battery_j:      float = 0.0    # estimated remaining battery energy
    flywheel_j:     float = 0.0    # flywheel kinetic energy
    total_j:        float = 0.0
    regen_total_j:  float = 0.0    # cumulative recovered energy this flight
    assist_total_j: float = 0.0    # cumulative energy discharged to motors

    def update(self, fw: FlywheelTelemetry, fc: FlightTelemetry):
        self.flywheel_j = fw.energy_j
        # Battery estimate: rough from voltage (4S nominal 14.8V, 3000mAh = 159,840 J)
        v_pct = max(0, min(1, (fc.battery_v - 13.2) / (16.8 - 13.2)))
        self.battery_j  = v_pct * 159_840
        self.total_j    = self.battery_j + self.flywheel_j


# ─── VESC Interface ───────────────────────────────────────────────────────────

class VESCInterface:
    """
    Communicates with VESC 4.12 over UART.
    Implements basic VESC packet protocol for RPM control and telemetry.
    Falls back to simulation if hardware not available.
    """

    VESC_COMM_GET_VALUES  = 4
    VESC_COMM_SET_RPM     = 8
    VESC_COMM_SET_CURRENT = 6

    def __init__(self, port: str, baud: int = 115200, sim: bool = False):
        self.sim  = sim
        self._rpm_setpoint = FLYWHEEL_RPM_IDLE
        self._ser = None
        self._lock = threading.Lock()

        # Simulation state
        self._sim_rpm     = 0.0
        self._sim_temp    = 25.0
        self._sim_voltage = 14.8

        if not sim:
            try:
                if serial is None:
                    raise ImportError("pyserial not installed")
                self._ser = serial.Serial(port, baud, timeout=0.1)
                log.info(f"VESC connected on {port} @ {baud}")
            except Exception as e:
                log.warning(f"VESC UART failed ({e}) — switching to simulation")
                self.sim = True

    def set_rpm(self, rpm: float):
        """Command flywheel to target RPM."""
        rpm = max(0, min(FLYWHEEL_RPM_MAX, rpm))
        self._rpm_setpoint = rpm
        if self.sim:
            return
        # VESC COMM_SET_RPM packet (simplified)
        erpm = int(rpm * 7)  # 7 pole pairs for RS2205
        payload = erpm.to_bytes(4, 'big', signed=True)
        self._send_packet(self.VESC_COMM_SET_RPM, payload)

    def set_brake_current(self, amps: float):
        """Apply regenerative braking current."""
        amps = max(-15.0, min(0.0, -abs(amps)))  # always negative for regen
        if self.sim:
            # Simulate energy recovery: reduce RPM proportional to brake
            self._sim_rpm = max(FLYWHEEL_RPM_MIN,
                                self._sim_rpm + amps * 200 * 0.05)
            return
        payload = int(amps * 1000).to_bytes(4, 'big', signed=True)
        self._send_packet(self.VESC_COMM_SET_CURRENT, payload)

    def get_telemetry(self) -> FlywheelTelemetry:
        t = FlywheelTelemetry()
        if self.sim:
            # Simulate flywheel dynamics
            target = self._rpm_setpoint
            diff   = target - self._sim_rpm
            # Spin up/down at ~500 RPM/s
            self._sim_rpm += max(-500, min(500, diff)) * 0.05
            self._sim_rpm  = max(0, self._sim_rpm)
            t.rpm       = self._sim_rpm
            t.voltage_v = self._sim_voltage
            t.current_a = abs(diff) / 5000 * 25   # simulated current
            t.temp_c    = min(65, 25 + t.current_a * 1.5)
        else:
            t = self._read_values()

        t.update_energy()
        return t

    def _send_packet(self, command: int, payload: bytes):
        if self._ser is None:
            return
        with self._lock:
            length  = len(payload) + 1
            packet  = bytes([2, length, command]) + payload
            crc     = self._crc16(bytes([command]) + payload)
            packet += crc.to_bytes(2, 'big') + bytes([3])
            self._ser.write(packet)

    def _read_values(self) -> FlywheelTelemetry:
        # Send GET_VALUES request and parse response
        self._send_packet(self.VESC_COMM_GET_VALUES, b'')
        time.sleep(0.01)
        t = FlywheelTelemetry()
        if self._ser and self._ser.in_waiting > 0:
            data = self._ser.read(self._ser.in_waiting)
            # Parse VESC response (simplified — full impl needs proper framing)
            if len(data) >= 25:
                t.temp_c    = int.from_bytes(data[3:5],   'big') / 10
                t.current_a = int.from_bytes(data[5:9],   'big', signed=True) / 100
                t.voltage_v = int.from_bytes(data[15:17], 'big') / 10
                erpm        = int.from_bytes(data[23:27], 'big', signed=True)
                t.rpm       = abs(erpm) / 7  # 7 pole pairs
        return t

    @staticmethod
    def _crc16(data: bytes) -> int:
        crc = 0
        for b in data:
            crc ^= b << 8
            for _ in range(8):
                crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        return crc & 0xFFFF


# ─── MAVLink Interface ────────────────────────────────────────────────────────

class FCInterface:
    """
    MAVLink interface to ArduCopter on H743.
    Reads telemetry, monitors flight state for regen triggers.
    """

    def __init__(self, connection: str, baud: int = 115200, sim: bool = False):
        self.sim  = sim
        self._mav = None
        self._telem = FlightTelemetry()
        self._lock  = threading.Lock()

        # Sim state
        self._sim_alt  = 10.0
        self._sim_vz   = 0.0
        self._sim_armed = True

        if not sim:
            try:
                if mavutil is None:
                    raise ImportError("pymavlink not installed")
                self._mav = mavutil.mavlink_connection(connection, baud=baud)
                self._mav.wait_heartbeat(timeout=5)
                log.info(f"FC connected: system {self._mav.target_system}")
                # Request data streams
                self._request_streams()
            except Exception as e:
                log.warning(f"FC MAVLink failed ({e}) — switching to simulation")
                self.sim = True

    def get_telemetry(self) -> FlightTelemetry:
        if self.sim:
            return self._sim_telemetry()
        return self._read_mavlink()

    def send_flywheel_rpm(self, rpm: float):
        """Broadcast flywheel RPM to the FC as NAMED_VALUE_FLOAT 'FWRPM'.

        Consumed by the flywheel_coupling.lua applet on the flight
        controller for gain scheduling and overspeed warnings.
        """
        if self.sim or self._mav is None:
            return
        self._mav.mav.named_value_float_send(
            int(time.time() * 1000) & 0xFFFFFFFF,
            b"FWRPM",
            rpm,
        )

    def _sim_telemetry(self) -> FlightTelemetry:
        """Simulate a simple hover → descend → ascend cycle."""
        t = time.time()
        cycle = t % 30
        if cycle < 10:
            self._sim_vz = 0.0      # hover
        elif cycle < 18:
            self._sim_vz = 1.5      # descend 1.5 m/s
        elif cycle < 26:
            self._sim_vz = -1.5     # ascend
        else:
            self._sim_vz = 0.0      # hover

        self._sim_alt = max(2, self._sim_alt - self._sim_vz * 0.05)

        with self._lock:
            self._telem.alt_m       = self._sim_alt
            self._telem.vz_ms       = self._sim_vz
            self._telem.armed       = self._sim_armed
            self._telem.mode        = "GUIDED"
            self._telem.battery_v   = 15.2
            self._telem.battery_pct = 85.0
            self._telem.timestamp   = time.time()
        return self._telem

    def _read_mavlink(self) -> FlightTelemetry:
        # Drain everything queued since the last tick — telemetry streams
        # arrive faster than the 20Hz loop, one message per tick falls behind.
        updated = False
        while True:
            msg = self._mav.recv_match(
                type=['GLOBAL_POSITION_INT', 'ATTITUDE', 'VFR_HUD',
                      'SYS_STATUS', 'BATTERY_STATUS', 'HEARTBEAT'],
                blocking=False
            )
            if msg is None:
                break

            with self._lock:
                mt = msg.get_type()
                if mt == 'GLOBAL_POSITION_INT':
                    self._telem.lat   = msg.lat / 1e7
                    self._telem.lon   = msg.lon / 1e7
                    self._telem.alt_m = msg.relative_alt / 1000
                    self._telem.vx_ms = msg.vx / 100
                    self._telem.vy_ms = msg.vy / 100
                    self._telem.vz_ms = msg.vz / 100
                    speed = math.sqrt(self._telem.vx_ms**2 + self._telem.vy_ms**2)
                    self._telem.groundspeed_ms = speed
                elif mt == 'ATTITUDE':
                    self._telem.roll_deg  = math.degrees(msg.roll)
                    self._telem.pitch_deg = math.degrees(msg.pitch)
                    self._telem.yaw_deg   = math.degrees(msg.yaw)
                elif mt == 'BATTERY_STATUS':
                    if msg.battery_remaining >= 0:
                        self._telem.battery_pct = msg.battery_remaining
                    if msg.voltages[0] != 65535:
                        self._telem.battery_v = msg.voltages[0] / 1000
                elif mt == 'HEARTBEAT':
                    if msg.type not in (mavutil.mavlink.MAV_TYPE_GCS,
                                        mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER):
                        self._telem.armed = bool(msg.base_mode & 0x80)
                        self._telem.mode  = mavutil.mode_string_v10(msg)
                updated = True

        if updated:
            with self._lock:
                self._telem.timestamp = time.time()
        return self._telem

    def _request_streams(self):
        if self._mav is None:
            return
        for stream_id, rate in [
            (mavutil.mavlink.MAV_DATA_STREAM_POSITION,    5),
            (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1,     10),
            (mavutil.mavlink.MAV_DATA_STREAM_EXTRA2,      5),
            (mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 2),
        ]:
            self._mav.mav.request_data_stream_send(
                self._mav.target_system,
                self._mav.target_component,
                stream_id, rate, 1
            )


# ─── Momentum Manager ─────────────────────────────────────────────────────────

class MomentumManager:
    """
    Core decision engine.

    Every 50ms:
      1. Poll FC and VESC telemetry
      2. Evaluate energy state
      3. Decide flywheel mode (idle / charge / regen / discharge)
      4. Command VESC accordingly
      5. Log to ring buffer

    Decision logic:
      DESCENDING + flywheel below max → REGEN (capture PE)
      ASCENDING  + flywheel has charge → DISCHARGE (assist climb)
      HOVER      + flywheel below idle → CHARGING
      MANEUVERING (high bank) → pre-charge to BOOST setpoint
      FAULT      → hold last safe RPM, alert
    """

    LOOP_HZ = 20   # 50ms loop

    def __init__(self, vesc: VESCInterface, fc: FCInterface, sim: bool = False):
        self.vesc = vesc
        self.fc   = fc
        self.sim  = sim

        self.fw_telem  = FlywheelTelemetry()
        self.fc_telem  = FlightTelemetry()
        self.budget    = EnergyBudget()

        self._mode     = FlywheelMode.IDLE
        self._running  = False
        self._thread   = None
        self._lock     = threading.Lock()

        # Ring buffers for logging
        self._fw_history  = deque(maxlen=TELEM_BUFFER)
        self._fc_history  = deque(maxlen=TELEM_BUFFER)
        self._event_log   = deque(maxlen=200)

        # Stats
        self._regen_j_total  = 0.0
        self._assist_j_total = 0.0
        self._loop_count     = 0
        self._start_time     = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background management loop."""
        self._running   = True
        self._start_time = time.time()
        self._thread    = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("MomentumManager started")

    def stop(self):
        """Gracefully stop the loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.vesc.set_rpm(0)
        log.info("MomentumManager stopped")

    @property
    def flywheel_mode(self) -> FlywheelMode:
        return self._mode

    @property
    def charge_pct(self) -> float:
        return self.fw_telem.charge_pct

    @property
    def effective_turn_radius(self) -> float:
        """
        Dynamic turn radius for Dubins planner.
        Exported so path planner can query directly.

        High charge → tighter turns allowed (gyroscopic assist available)
        Low charge  → enforce wider turns (protect stability)
        """
        charge = self.fw_telem.charge_pct / 100
        r_min = self._dubins_r_min()
        r_max = r_min * 2.0
        return r_max - (r_max - r_min) * charge

    def request_boost(self):
        """
        Call before a demanding maneuver sequence.
        Spins flywheel up to BOOST setpoint.
        Returns when charged or timeout.
        """
        log.info(f"Boost requested — spinning up to {FLYWHEEL_RPM_BOOST} RPM")
        self.vesc.set_rpm(FLYWHEEL_RPM_BOOST)
        timeout = time.time() + 15
        while time.time() < timeout:
            t = self.vesc.get_telemetry()
            if t.rpm >= FLYWHEEL_RPM_BOOST * 0.95:
                log.info(f"Boost ready: {t.rpm:.0f} RPM")
                return True
            time.sleep(0.2)
        log.warning("Boost timeout — proceeding with available charge")
        return False

    def get_stats(self) -> dict:
        """Return current session energy statistics."""
        elapsed = time.time() - (self._start_time or time.time())
        return {
            "session_s":       round(elapsed, 1),
            "loop_count":      self._loop_count,
            "flywheel_rpm":    round(self.fw_telem.rpm, 0),
            "flywheel_charge": round(self.fw_telem.charge_pct, 1),
            "flywheel_mode":   self._mode.name,
            "flywheel_j":      round(self.fw_telem.energy_j, 1),
            "regen_j_total":   round(self._regen_j_total, 2),
            "assist_j_total":  round(self._assist_j_total, 2),
            "net_recovery_j":  round(self._regen_j_total - self._assist_j_total, 2),
            "effective_r_m":   round(self.effective_turn_radius, 2),
            "turn_radius_m":   round(self._dubins_r_min(), 2),
            "drone_alt_m":     round(self.fc_telem.alt_m, 1),
            "drone_vz_ms":     round(self.fc_telem.vz_ms, 2),
            "battery_pct":     round(self.fc_telem.battery_pct, 1),
        }

    # ── Internal Loop ─────────────────────────────────────────────────────────

    def _loop(self):
        interval = 1.0 / self.LOOP_HZ
        while self._running:
            t0 = time.time()
            try:
                self._tick()
            except Exception as e:
                log.error(f"Loop error: {e}")
                self._set_mode(FlywheelMode.FAULT)
            elapsed = time.time() - t0
            sleep_t = max(0, interval - elapsed)
            time.sleep(sleep_t)

    def _tick(self):
        """Single loop iteration."""
        # 1. Poll telemetry
        fw = self.vesc.get_telemetry()
        fc = self.fc.get_telemetry()

        with self._lock:
            self.fw_telem = fw
            self.fc_telem = fc
            self.budget.update(fw, fc)
            self._fw_history.append(fw)
            self._fc_history.append(fc)

        # 2. Decide mode
        new_mode = self._decide_mode(fw, fc)
        if new_mode != self._mode:
            self._log_event(f"Mode: {self._mode.name} → {new_mode.name} "
                            f"| RPM={fw.rpm:.0f} vz={fc.vz_ms:.2f}")
            self._set_mode(new_mode)

        # 3. Execute mode
        self._execute_mode(fw, fc)

        self._loop_count += 1

        # Broadcast flywheel RPM to FC at 5Hz for the Lua coupling applet
        if self._loop_count % (self.LOOP_HZ // 5) == 0:
            self.fc.send_flywheel_rpm(fw.rpm)

        # 4. Periodic status log (every 5s)
        if self._loop_count % (self.LOOP_HZ * 5) == 0:
            s = self.get_stats()
            log.info(
                f"RPM={s['flywheel_rpm']:.0f} "
                f"({s['flywheel_charge']:.0f}%) "
                f"mode={s['flywheel_mode']:10s} "
                f"regen={s['regen_j_total']:.1f}J "
                f"alt={s['drone_alt_m']:.1f}m "
                f"vz={s['drone_vz_ms']:+.2f}m/s "
                f"r_eff={s['effective_r_m']:.1f}m"
            )

    def _decide_mode(self, fw: FlywheelTelemetry, fc: FlightTelemetry) -> FlywheelMode:
        """State machine decision logic."""

        # Fault conditions
        if fw.temp_c > 80:
            log.warning(f"VESC overheat: {fw.temp_c:.0f}°C")
            return FlywheelMode.FAULT
        if fw.rpm > FLYWHEEL_RPM_MAX * 1.05:
            log.warning(f"Flywheel overspeed: {fw.rpm:.0f} RPM")
            return FlywheelMode.FAULT

        # Not armed / on ground — just idle
        if not fc.armed:
            return FlywheelMode.IDLE

        # Descending meaningfully → capture energy
        if fc.descending and fw.charge_pct < 98:
            return FlywheelMode.REGEN

        # Ascending with charge available → assist
        if fc.ascending and fw.energy_j > KE_MIN * 2:
            return FlywheelMode.DISCHARGE

        # High bank angle (maneuvering) → stay charged
        bank = max(abs(fc.roll_deg), abs(fc.pitch_deg))
        if bank > 20 and fw.charge_pct < 60:
            return FlywheelMode.CHARGING

        # Below idle RPM → charge back up
        if fw.rpm < FLYWHEEL_RPM_IDLE * 0.9:
            return FlywheelMode.CHARGING

        # Holding is fine
        if fw.rpm >= FLYWHEEL_RPM_IDLE * 0.9:
            return FlywheelMode.HOLDING

        return FlywheelMode.IDLE

    def _execute_mode(self, fw: FlywheelTelemetry, fc: FlightTelemetry):
        """Send commands to VESC based on current mode."""

        if self._mode == FlywheelMode.IDLE:
            self.vesc.set_rpm(FLYWHEEL_RPM_IDLE * 0.5)

        elif self._mode == FlywheelMode.CHARGING:
            self.vesc.set_rpm(FLYWHEEL_RPM_IDLE)

        elif self._mode == FlywheelMode.HOLDING:
            self.vesc.set_rpm(FLYWHEEL_RPM_IDLE)

        elif self._mode == FlywheelMode.REGEN:
            # Scale regen current with descent speed
            vz_clamped  = min(abs(fc.vz_ms), 3.0)
            regen_amps  = -(vz_clamped / 3.0) * 12.0   # max -12A regen
            self.vesc.set_brake_current(regen_amps)
            # Estimate energy recovered (power = V × I × efficiency × dt)
            recovered = abs(fw.voltage_v * regen_amps * REGEN_EFFICIENCY / self.LOOP_HZ)
            self._regen_j_total += recovered

        elif self._mode == FlywheelMode.DISCHARGE:
            # Gentle discharge — ramp down RPM to release energy to bus
            target = max(FLYWHEEL_RPM_MIN, fw.rpm - 500)
            self.vesc.set_rpm(target)
            # Estimate energy discharged
            prev_ke      = fw.energy_j
            next_omega   = target * 2*math.pi/60
            next_ke      = 0.5 * FLYWHEEL_I * next_omega**2
            discharged   = max(0, prev_ke - next_ke)
            self._assist_j_total += discharged

        elif self._mode == FlywheelMode.FAULT:
            # Hold current RPM, do not change anything
            pass

    def _set_mode(self, mode: FlywheelMode):
        self._mode = mode

    def _log_event(self, msg: str):
        entry = {"t": time.time(), "msg": msg}
        self._event_log.append(entry)
        log.debug(f"EVENT: {msg}")

    def _dubins_r_min(self, speed_ms: float = 5.0) -> float:
        bank_rad = math.radians(BANK_MAX_DEG)
        return speed_ms**2 / (G * math.tan(bank_rad))


# ─── Wiring check  ────────────────────────────────────────────────────────────

def check_hardware(vesc_port: str, fc_port: str) -> dict:
    """Quick connectivity check before starting."""
    results = {}

    if serial:
        for name, port in [("VESC", vesc_port), ("FC", fc_port)]:
            try:
                s = serial.Serial(port, 115200, timeout=0.5)
                s.close()
                results[name] = "OK"
            except Exception as e:
                results[name] = f"FAIL ({e})"
    else:
        results["serial"] = "pyserial not installed"

    return results


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FlyGimbal Momentum Manager")
    parser.add_argument("--fc",   default="udp:127.0.0.1:14550", help="FC MAVLink connection")
    parser.add_argument("--vesc", default="/dev/ttyS3",           help="VESC UART port")
    parser.add_argument("--fc-baud",   type=int, default=115200)
    parser.add_argument("--vesc-baud", type=int, default=115200)
    parser.add_argument("--sim",  action="store_true",            help="Full simulation mode")
    parser.add_argument("--boost-test", action="store_true",      help="Run boost sequence test")
    args = parser.parse_args()

    if not args.sim:
        log.info("Checking hardware connectivity...")
        hw = check_hardware(args.vesc, args.fc)
        for k, v in hw.items():
            log.info(f"  {k}: {v}")

    vesc = VESCInterface(args.vesc, args.vesc_baud, sim=args.sim)
    fc   = FCInterface(args.fc,   args.fc_baud,   sim=args.sim)
    mgr  = MomentumManager(vesc, fc, sim=args.sim)

    mode = "SIMULATION" if args.sim else "HARDWARE"
    log.info(f"Starting in {mode} mode")
    mgr.start()

    if args.boost_test:
        log.info("Running boost test...")
        time.sleep(2)
        mgr.request_boost()

    try:
        while True:
            time.sleep(5)
            s = mgr.get_stats()
            print(
                f"\n{'─'*55}\n"
                f"  RPM:      {s['flywheel_rpm']:>8.0f}  ({s['flywheel_charge']:.1f}%)\n"
                f"  Mode:     {s['flywheel_mode']:>12s}\n"
                f"  Energy:   {s['flywheel_j']:>8.1f} J\n"
                f"  Regen:  + {s['regen_j_total']:>8.2f} J  (recovered)\n"
                f"  Assist: - {s['assist_j_total']:>8.2f} J  (discharged)\n"
                f"  Net:      {s['net_recovery_j']:>8.2f} J\n"
                f"  Turn R:   {s['effective_r_m']:>8.2f} m  (effective)\n"
                f"  Alt:      {s['drone_alt_m']:>8.1f} m\n"
                f"  Battery:  {s['battery_pct']:>8.1f} %\n"
                f"{'─'*55}"
            )
    except KeyboardInterrupt:
        log.info("Shutting down...")
        mgr.stop()
        s = mgr.get_stats()
        log.info(
            f"Session summary — "
            f"Regen: {s['regen_j_total']:.2f}J  "
            f"Assist: {s['assist_j_total']:.2f}J  "
            f"Net: {s['net_recovery_j']:.2f}J  "
            f"Loops: {s['loop_count']}"
        )


if __name__ == "__main__":
    main()

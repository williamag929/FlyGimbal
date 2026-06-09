"""
GyroDrone -- Full Physics Simulation
src/simulation/gyrodrone_sim.py

Simulates the complete GyroDrone system:
  - Flywheel FESS (kinetic energy storage + gyroscopic stabilization)
  - Thrust-vectoring gimbal (2 of 4 motors on Savox SH-0257MG servos)
  - Disc-frame 6-DOF rigid body dynamics (proper cascade controller)
  - Momentum-aware Dubins path following

Runs standalone -- no hardware required.

Dependencies:
    pip install numpy matplotlib

Usage:
    python gyrodrone_sim.py                       # default circuit
    python gyrodrone_sim.py --mission figure8
    python gyrodrone_sim.py --mission lawnmower
    python gyrodrone_sim.py --no-regen            # disable FESS regen
    python gyrodrone_sim.py --dt 0.005            # higher fidelity
"""

import math
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from dataclasses import dataclass
from typing import List, Tuple


# ---- Physical constants -------------------------------------------------------

G       = 9.81      # m/s^2
RHO     = 1.225     # kg/m^3

# ---- Airframe (FRAME_SPEC.md) -------------------------------------------------

FRAME_MASS   = 0.180    # kg  (CF plates)
MOTOR_MASS   = 0.052    # kg  (4x Emax 2807 + ESC)
BATTERY_MASS = 0.200    # kg  (4S 2200mAh)
FW_MASS      = 0.145    # kg  (rotor + motor + bearing)
AVIONICS_MASS= 0.080    # kg  (FC, GPS, VTX)
MASS         = FRAME_MASS + 4*MOTOR_MASS + BATTERY_MASS + FW_MASS + AVIONICS_MASS

R_FRAME      = 0.200    # m   outer disc radius
R_MOTOR      = 0.185    # m   motor arm radius (motor positions)
L_ARM        = R_MOTOR * math.sin(math.radians(45))  # effective moment arm for X-config

# Inertia tensor (body frame, disc approximation)
# I_zz: ring + 4 point masses at R_MOTOR
I_ZZ = FRAME_MASS * R_FRAME**2 + 4 * MOTOR_MASS * R_MOTOR**2
# I_xx = I_yy = I_zz/2 for thin uniform disc
I_XX = I_ZZ * 0.5
I_YY = I_ZZ * 0.5

# ---- Propulsion ---------------------------------------------------------------

# T = KT * omega^2,  Q = KQ * omega^2
KT           = 1.1e-5   # N/(rad/s)^2  (5-inch prop at standard air density)
KQ           = 1.2e-7   # Nm/(rad/s)^2
OMEGA_MAX    = 3000.0   # rad/s (~28 600 RPM at 4S for 2300KV)
OMEGA_HOVER  = math.sqrt(MASS * G / (4 * KT))   # rad/s per motor to hover
THROTTLE_HOV = OMEGA_HOVER / OMEGA_MAX           # fraction

# Motor positions (angle from +X, CCW), spin directions (+1=CCW, -1=CW)
# Indices: 0=FR(45), 1=BR(135), 2=BL(225), 3=FL(315)
MOTOR_SPIN   = [+1, -1, +1, -1]    # alternating for yaw balance

# ---- Flywheel (FLYWHEEL_SPEC.md) ----------------------------------------------

FW_I         = 1.16e-4  # kg*m^2  (as-built v01 rotor, 118g — measured from STL)
FW_RPM_MAX   = 20_000
FW_RPM_MIN   =  5_000
FW_RPM_IDLE  = 15_000
FW_FRIC      = 0.002    # Nm bearing friction
FW_REGEN_EFF = 0.75     # regenerative braking efficiency
FW_SPINUP_TQ = 0.08     # Nm max motor torque

# ---- Gimbal (GIMBAL_SPEC.md) --------------------------------------------------

GIMBAL_MAX   = math.radians(15.0)           # +/-15 degrees
GIMBAL_RATE  = math.radians(60 / 0.07)      # 857 deg/s  Savox SH-0257MG
GIMBAL_THR_LO= 0.30                         # disable servo below this throttle

# ---- Aerodynamics -------------------------------------------------------------

CD_BODY      = 0.40
A_FRONT      = math.pi * R_FRAME**2 * 0.3   # effective frontal area


# ==============================================================================
# Flywheel
# ==============================================================================

class Flywheel:
    """
    FESS rotor: RPM integration, bearing losses, regenerative braking,
    and gyroscopic angular momentum output.
    """

    def __init__(self, init_rpm: float = FW_RPM_IDLE, regen: bool = True):
        self.rpm         = float(init_rpm)
        self.regen       = regen
        self.regen_power = 0.0   # W recovered this step

    # ---- derived quantities ---------------------------------------------------

    @property
    def omega(self) -> float:
        return self.rpm * 2*math.pi / 60

    @property
    def energy(self) -> float:
        return 0.5 * FW_I * self.omega**2

    @property
    def charge(self) -> float:
        r = max(FW_RPM_MIN, min(FW_RPM_MAX, self.rpm))
        return (r - FW_RPM_MIN) / (FW_RPM_MAX - FW_RPM_MIN)

    @property
    def L(self) -> float:
        """Angular momentum magnitude L = I*omega (kg*m^2/s)."""
        return FW_I * self.omega

    # ---- integration ---------------------------------------------------------

    def step(self, dt: float, vz_ned: float) -> None:
        """
        Advance flywheel by dt.
        vz_ned > 0 means descending in NED (positive = down).
        """
        w = self.omega

        tau_fric  = -FW_FRIC * (1.0 if w >= 0 else -1.0)
        # maintain idle RPM
        err       = FW_RPM_IDLE - self.rpm
        tau_motor = max(-FW_SPINUP_TQ, min(FW_SPINUP_TQ, err * 1e-4))

        # regen on descent
        tau_regen = 0.0
        self.regen_power = 0.0
        if self.regen and vz_ned > 0.3 and self.rpm < FW_RPM_MAX * 0.95:
            tau_regen        = min(0.04, vz_ned * 0.015)
            self.regen_power = tau_regen * w * FW_REGEN_EFF

        alpha = (tau_fric + tau_motor + tau_regen) / FW_I
        w_new = w + alpha * dt
        w_new = max(FW_RPM_MIN * 2*math.pi/60, min(FW_RPM_MAX * 2*math.pi/60, w_new))
        self.rpm = w_new * 60 / (2*math.pi)


# ==============================================================================
# Gimbal
# ==============================================================================

class Gimbal:
    """
    Two thrust-vectoring servos on the front-left (FL) and front-right (FR)
    motor arms. Rate-limited first-order response.
    """

    def __init__(self):
        self.fl = 0.0   # rad
        self.fr = 0.0   # rad

    def command(self, cmd_fl: float, cmd_fr: float, dt: float, thr: float) -> None:
        if thr < GIMBAL_THR_LO:
            cmd_fl = cmd_fr = 0.0
        cmd_fl = max(-GIMBAL_MAX, min(GIMBAL_MAX, cmd_fl))
        cmd_fr = max(-GIMBAL_MAX, min(GIMBAL_MAX, cmd_fr))
        max_d  = GIMBAL_RATE * dt
        self.fl += max(-max_d, min(max_d, cmd_fl - self.fl))
        self.fr += max(-max_d, min(max_d, cmd_fr - self.fr))


# ==============================================================================
# Motor Array
# ==============================================================================

class Motors:
    """
    Four motors in X-configuration on the disc frame.
    Mixing: throttle (collective), roll, pitch, yaw.
    Produces individual omega values; thrust/torque computed from physics.
    """

    def __init__(self):
        self.omega = np.full(4, OMEGA_HOVER)  # rad/s

    def set_wrench(self, T_cmd: float, tau_roll: float, tau_pitch: float, tau_yaw: float) -> None:
        """
        Wrench allocation: compute motor speeds from desired total thrust and torques.
        Decouples altitude throttle from attitude authority.

        T_cmd   : desired total thrust (N)
        tau_*   : desired body-frame torques (Nm)
        """
        w2_base = T_cmd / (4 * KT)                              # omega^2 per motor (hover)
        w_base  = math.sqrt(max(0.0, w2_base))

        # Linear approximation: d_omega = d_tau / (4 * KT * 2 * w_base * arm)
        # Front-rear differential for pitch:  tau_p = 2*(T_front-T_rear)*L_ARM
        dw_p = tau_pitch / (4 * KT * 2 * w_base * L_ARM) if w_base > 1.0 else 0.0
        # Left-right differential for roll:
        dw_r = tau_roll  / (4 * KT * 2 * w_base * L_ARM) if w_base > 1.0 else 0.0
        # Yaw via reaction torque: tau_y = 4 * KQ * 2 * w_base * dw_y (alternating signs)
        dw_y = tau_yaw   / (4 * KQ * 2 * w_base)          if w_base > 1.0 else 0.0

        w = np.array([
            w_base + dw_p - dw_r + dw_y,   # FR
            w_base - dw_p - dw_r - dw_y,   # BR
            w_base - dw_p + dw_r + dw_y,   # BL
            w_base + dw_p + dw_r - dw_y,   # FL
        ])
        self.omega = np.clip(w, 0.0, OMEGA_MAX)

    @property
    def thrusts(self) -> np.ndarray:
        return KT * self.omega**2

    @property
    def T(self) -> float:
        return float(np.sum(self.thrusts))

    @property
    def tau_roll(self) -> float:
        """Roll torque from differential thrust (body +X fwd, +Y right, +Z down).
        Positive roll = right side down = left motors spin faster.
        Motors: FR(0)=+Y, BR(1)=+Y, BL(2)=-Y, FL(3)=-Y
        """
        T = self.thrusts
        return (T[2] + T[3] - T[0] - T[1]) * L_ARM

    @property
    def tau_pitch(self) -> float:
        """Positive pitch = nose up = rear motors spin faster.
        Motors: FR(0)=front, BR(1)=rear, BL(2)=rear, FL(3)=front
        """
        T = self.thrusts
        return (T[0] + T[3] - T[1] - T[2]) * L_ARM  # front - rear = nose-UP positive

    @property
    def tau_yaw(self) -> float:
        """Yaw torque from motor reaction torques."""
        return float(np.sum([
            MOTOR_SPIN[i] * KQ * self.omega[i]**2 for i in range(4)
        ]))


# ==============================================================================
# 6-DOF Dynamics
# ==============================================================================

@dataclass
class State:
    # NED position (m)
    x: float = 0.0; y: float = 0.0; z: float = 0.0
    # NED velocity (m/s)
    vx: float = 0.0; vy: float = 0.0; vz: float = 0.0
    # Euler angles (rad): roll phi, pitch theta, yaw psi
    phi: float = 0.0; theta: float = 0.0; psi: float = 0.0
    # Body angular rates (rad/s)
    p: float = 0.0; q: float = 0.0; r: float = 0.0

    @property
    def alt(self) -> float:
        return -self.z

    @property
    def speed_2d(self) -> float:
        return math.sqrt(self.vx**2 + self.vy**2)


def _wrap(a: float) -> float:
    """Wrap angle to [-pi, pi] in O(1) — no while loop."""
    return math.atan2(math.sin(a), math.cos(a))


class Wind:
    """
    Steady wind + first-order Gauss-Markov gusts (Dryden-lite).

    direction_deg is the direction the wind blows TOWARD (NED heading).
    Gusts decorrelate over tau seconds; vertical gusts are 1/3 horizontal.
    """

    def __init__(self, rng, speed: float = 0.0, direction_deg: float = 0.0,
                 gust_sigma: float = None, tau: float = 2.0):
        self.rng = rng
        rad = math.radians(direction_deg)
        self.steady = np.array([speed*math.cos(rad), speed*math.sin(rad), 0.0])
        self.gust_sigma = 0.3*speed if gust_sigma is None else gust_sigma
        self.tau  = tau
        self.gust = np.zeros(3)

    def step(self, dt: float) -> np.ndarray:
        """Advance gust state, return current wind vector (NED, m/s)."""
        sig = np.array([self.gust_sigma, self.gust_sigma, self.gust_sigma/3.0])
        self.gust += (-self.gust/self.tau)*dt \
                     + sig*math.sqrt(2.0*dt/self.tau)*self.rng.standard_normal(3)
        return self.steady + self.gust


class SensorNoise:
    """
    Measurement model: the controller sees this, not truth.

    - position: GPS-like Gauss-Markov bias (tau=10s, sigma=0.4m) + 5cm white
    - velocity: 0.1 m/s white
    - attitude: 0.3 deg white (EKF-quality estimate)
    - gyro rates: 0.02 rad/s white
    """

    def __init__(self, rng, scale: float = 1.0):
        self.rng      = rng
        self.scale    = scale
        self.pos_bias = np.zeros(3)
        self.tau      = 10.0

    def measure(self, s: "State", dt: float) -> "State":
        sc, rng = self.scale, self.rng
        self.pos_bias += (-self.pos_bias/self.tau)*dt \
                         + 0.4*sc*math.sqrt(2.0*dt/self.tau)*rng.standard_normal(3)
        n = lambda sig: rng.normal(0.0, sig*sc)
        return State(
            x=s.x + self.pos_bias[0] + n(0.05),
            y=s.y + self.pos_bias[1] + n(0.05),
            z=s.z + self.pos_bias[2] + n(0.05),
            vx=s.vx + n(0.1), vy=s.vy + n(0.1), vz=s.vz + n(0.1),
            phi=s.phi + n(0.005), theta=s.theta + n(0.005), psi=s.psi + n(0.005),
            p=s.p + n(0.02), q=s.q + n(0.02), r=s.r + n(0.02),
        )


class Dynamics:
    """
    6-DOF rigid-body integration for the GyroDrone disc-frame.

    Control cascade:
        position error --> desired roll/pitch (attitude setpoint)
        attitude error --> motor differential mix
        motor omegas   --> forces and torques (physics)
        forces/torques --> state derivative --> Euler integration
    """

    def __init__(self, alt0: float = 10.0, regen: bool = True,
                 wind: Wind = None, noise: SensorNoise = None):
        self.s       = State(z=-alt0)
        self.motors  = Motors()
        self.gimbal  = Gimbal()
        self.fw      = Flywheel(regen=regen)
        self.wind    = wind
        self.noise   = noise

        # Integrators
        self._i_alt  = 0.0
        self._i_yaw  = 0.0

    # ---- controller ----------------------------------------------------------

    def _control(
        self,
        dt: float,
        tx: float, ty: float,
        t_alt: float,
        t_yaw: float,
    ) -> float:
        """Returns current throttle (for gimbal enable check)."""
        # Control acts on MEASURED state when sensor noise is modelled
        s = self.noise.measure(self.s, dt) if self.noise else self.s
        cy, sy = math.cos(s.psi), math.sin(s.psi)

        # ---- outer loop: position -> desired horizontal acceleration ----
        # PD in NED then rotate to body for des_theta / des_phi
        # Units: Kp in (m/s^2)/m, Kd in (m/s^2)/(m/s)
        ex_n = tx - s.x; ey_n = ty - s.y
        ax_des_n = 0.5*ex_n - 1.0*s.vx   # desired accel in NED (m/s^2)
        ay_des_n = 0.5*ey_n - 1.0*s.vy

        # Limit max horizontal acceleration to 3 m/s^2
        amag = math.sqrt(ax_des_n**2 + ay_des_n**2)
        if amag > 3.0:
            ax_des_n *= 3.0/amag;  ay_des_n *= 3.0/amag

        # Rotate desired acceleration to body frame
        ax_des_b =  ax_des_n * cy + ay_des_n * sy
        ay_des_b = -ax_des_n * sy + ay_des_n * cy

        # Tilt angle from desired acceleration: theta = -ax/g  (nose-down → +X)
        TILT_MAX = 0.35  # rad (~20 degrees)
        des_theta = max(-TILT_MAX, min(TILT_MAX, -ax_des_b / G))
        des_phi   = max(-TILT_MAX, min(TILT_MAX,  ay_des_b / G))

        # ---- altitude controller (PI+D) ----
        alt_err     = t_alt - s.alt
        self._i_alt = max(-3.0, min(3.0, self._i_alt + alt_err*dt))
        thr = max(0.0, min(1.0, THROTTLE_HOV + 0.5*alt_err + 0.04*self._i_alt - 0.4*s.vz))

        # ---- yaw controller (PI+D) ----
        yaw_err     = _wrap(t_yaw - s.psi)
        self._i_yaw = max(-1.0, min(1.0, self._i_yaw + yaw_err*dt))
        yaw_cmd = max(-1.0, min(1.0, 2.0*yaw_err + 0.1*self._i_yaw - 0.5*s.r))

        # ---- inner loop: attitude PD -> desired angular accelerations ----
        # omega_n = 5 rad/s, zeta = 0.8  →  Kp=25, Kd=8  (rad/s^2 per rad error)
        alpha_p = 25.0*(des_phi   - s.phi)   - 8.0*s.p   # desired roll  accel (rad/s^2)
        alpha_q = 25.0*(des_theta - s.theta) - 8.0*s.q   # desired pitch accel
        alpha_r = 6.0 *yaw_err + 0.5*self._i_yaw - 4.0*s.r  # desired yaw accel

        # Desired torques (Nm) = I * alpha, clamped to physical limits
        T_cmd = max(0.0, MASS * G / max(0.1, math.cos(s.phi)*math.cos(s.theta)))
        T_cmd = max(0.0, min(4*KT*OMEGA_MAX**2, T_cmd))  # saturate at motor limit

        tau_r_max = I_XX * 50.0
        tau_p_max = I_YY * 50.0
        tau_y_max = I_ZZ * 10.0

        # Gyroscopic feed-forward: cancel coupling from flywheel angular momentum
        # p_dot_actual = (motors.tau_roll - L_fw*q) / I_XX
        # To get p_dot = alpha_p: set motors.tau_roll = I_XX*alpha_p + L_fw*q
        L_fw = self.fw.L
        tau_r = max(-tau_r_max, min(tau_r_max, I_XX * alpha_p + L_fw * s.q))
        tau_p = max(-tau_p_max, min(tau_p_max, I_YY * alpha_q - L_fw * s.p))
        tau_y = max(-tau_y_max, min(tau_y_max, I_ZZ * alpha_r))

        # Altitude: separate throttle computation (decoupled from attitude)
        alt_err     = t_alt - s.alt
        self._i_alt = max(-3.0, min(3.0, self._i_alt + alt_err*dt))
        T_alt       = MASS * G + MASS * (0.5*alt_err + 0.04*self._i_alt - 0.3*s.vz)
        T_cmd       = max(0.0, min(4*KT*OMEGA_MAX**2, T_alt /
                         max(0.2, math.cos(s.phi)*math.cos(s.theta))))

        self.motors.set_wrench(T_cmd, tau_r, tau_p, tau_y)

        thr = T_cmd / (4 * KT * OMEGA_MAX**2)   # for display / gimbal enable

        # ---- gimbals: pitch authority boost ----
        fw_scale = 0.5 + 0.5 * self.fw.charge
        g_cmd    = max(-GIMBAL_MAX, min(GIMBAL_MAX, (des_theta - s.theta) * fw_scale * 0.5))
        self.gimbal.command(g_cmd, g_cmd, dt, thr)
        return thr

    # ---- physics step --------------------------------------------------------

    def step(
        self,
        dt: float,
        tx: float, ty: float,
        t_alt: float = 10.0,
        t_yaw: float = 0.0,
    ) -> None:
        self._control(dt, tx, ty, t_alt, t_yaw)
        s = self.s

        cr = math.cos(s.phi);   sr = math.sin(s.phi)
        cp = math.cos(s.theta); sp = math.sin(s.theta)
        cy = math.cos(s.psi);   sy = math.sin(s.psi)

        # ---- thrust and vectored force in NED ----
        T = self.motors.T

        # Gimbal: front two motors (FR=0, FL=3) tilt in pitch plane
        T_front = float(np.sum(self.motors.thrusts[[0, 3]]))
        g_avg   = (self.gimbal.fl + self.gimbal.fr) / 2.0
        # extra forward force from tilted front motors (body-X direction)
        F_x_body = T_front * math.sin(g_avg)

        # Thrust vector in NED: F_thrust_NED = R_bn * [0, 0, -T]_body
        # R_bn (ZYX) third column: [cy*sp*cr+sy*sr, sy*sp*cr-cy*sr, cp*cr]
        # F_thrust_NED = -T * that column (minus sign: thrust in -z_body)
        # Nose-down (theta<0): sp<0 → Fx_ned>0 (forward) ✓
        Fx_ned = -(cy*sp*cr + sy*sr) * T - (cp*cy) * F_x_body
        Fy_ned = -(sy*sp*cr - cy*sr) * T - (cp*sy) * F_x_body
        Fz_ned = -(cp*cr)            * T + MASS*G   # gravity positive (NED)

        # ---- aerodynamic drag (on air-relative velocity, so wind pushes) ----
        if self.wind is not None:
            w = self.wind.step(dt)
            vrx, vry, vrz = s.vx - w[0], s.vy - w[1], s.vz - w[2]
        else:
            vrx, vry, vrz = s.vx, s.vy, s.vz
        v3d = math.sqrt(vrx**2 + vry**2 + vrz**2)
        if v3d > 0.05:
            drag = 0.5 * RHO * CD_BODY * A_FRONT * v3d**2
            Fx_ned -= drag * vrx / v3d
            Fy_ned -= drag * vry / v3d
            Fz_ned -= drag * vrz / v3d

        # ---- torques ----
        # Gyroscopic precession from flywheel (spin axis = body Z)
        # tau = L_fw x omega_body: couples pitch<->roll rates
        L_fw           = self.fw.L
        tau_gyro_roll  = -L_fw * s.q
        tau_gyro_pitch =  L_fw * s.p

        # Gimbal pitch boost (front motor moment arm)
        tau_pitch_gimbal = T_front * R_MOTOR * math.sin(g_avg)

        tau_roll  = self.motors.tau_roll  + tau_gyro_roll
        tau_pitch = self.motors.tau_pitch + tau_gyro_pitch + tau_pitch_gimbal
        tau_yaw   = self.motors.tau_yaw

        # ---- integrate ----
        s.vx += (Fx_ned / MASS) * dt
        s.vy += (Fy_ned / MASS) * dt
        s.vz += (Fz_ned / MASS) * dt
        s.x  += s.vx * dt
        s.y  += s.vy * dt
        s.z  += s.vz * dt

        s.p += (tau_roll  / I_XX) * dt
        s.q += (tau_pitch / I_YY) * dt
        s.r += (tau_yaw   / I_ZZ) * dt
        s.phi   = _wrap(s.phi   + s.p * dt)
        s.theta = _wrap(s.theta + s.q * dt)
        s.psi   = _wrap(s.psi   + s.r * dt)

        self.fw.step(dt, s.vz)


# ==============================================================================
# Inline Dubins Path  (no external dependency)
# ==============================================================================

def _mod2pi(x: float) -> float:
    v = x % (2*math.pi)
    return v if v >= 0 else v + 2*math.pi


def _dubins_LSL(a, b, d):
    sa, ca, sb, cb = math.sin(a), math.cos(a), math.sin(b), math.cos(b)
    psq = 2 + d*d - 2*math.cos(a-b) + 2*d*(sa-sb)
    if psq < 0: return None
    p   = math.sqrt(psq)
    th  = math.atan2(cb-ca, d+sa-sb)
    t   = _mod2pi(-a + th); q = _mod2pi(b - th)
    return ("L","S","L"), t, p, q, t+p+q


def _dubins_RSR(a, b, d):
    sa, ca, sb, cb = math.sin(a), math.cos(a), math.sin(b), math.cos(b)
    psq = 2 + d*d - 2*math.cos(a-b) + 2*d*(sb-sa)
    if psq < 0: return None
    p   = math.sqrt(psq)
    th  = math.atan2(ca-cb, d-sa+sb)
    t   = _mod2pi(a - th); q = _mod2pi(-b + th)
    return ("R","S","R"), t, p, q, t+p+q


def _dubins_LSR(a, b, d):
    sa, ca, sb, cb = math.sin(a), math.cos(a), math.sin(b), math.cos(b)
    psq = -2 + d*d + 2*math.cos(a-b) + 2*d*(sa+sb)
    if psq < 0: return None
    p   = math.sqrt(psq)
    th  = math.atan2(-ca-cb, d+sa+sb) - math.atan2(-2.0, p)
    t   = _mod2pi(-a + th); q = _mod2pi(-_mod2pi(b) + th)
    return ("L","S","R"), t, p, q, t+p+q


def _dubins_RSL(a, b, d):
    sa, ca, sb, cb = math.sin(a), math.cos(a), math.sin(b), math.cos(b)
    psq = -2 + d*d + 2*math.cos(a-b) - 2*d*(sa+sb)
    if psq < 0: return None
    p   = math.sqrt(psq)
    th  = math.atan2(ca+cb, d-sa-sb) - math.atan2(2.0, p)
    t   = _mod2pi(a - th); q = _mod2pi(b - th)
    return ("R","S","L"), t, p, q, t+p+q


def _arc(x0, y0, h0, rho, arc_len, left: bool):
    """Move along a circular arc of length arc_len (in meters)."""
    if abs(arc_len) < 1e-9:
        return x0, y0, h0
    sign  = +1 if left else -1
    dh    = sign * arc_len / rho
    cx    = x0 - sign * rho * math.sin(h0)
    cy    = y0 + sign * rho * math.cos(h0)
    h1    = _wrap(h0 + dh)
    x1    = cx + sign * rho * math.sin(h1)
    y1    = cy - sign * rho * math.cos(h1)
    return x1, y1, h1


def dubins_sample(
    q0: Tuple[float, float, float],
    q1: Tuple[float, float, float],
    rho: float,
    step: float = 0.4,
) -> List[Tuple[float, float, float]]:
    """Return sampled (x,y,heading) along the shortest Dubins path."""
    dx, dy = q1[0]-q0[0], q1[1]-q0[1]
    D = math.sqrt(dx*dx + dy*dy)
    if D < 1e-3:
        return [q0]

    d     = D / rho
    theta = _mod2pi(math.atan2(dy, dx))
    alpha = _mod2pi(q0[2] - theta)
    beta  = _mod2pi(q1[2] - theta)

    segs = [f(alpha, beta, d) for f in (_dubins_LSL, _dubins_RSR, _dubins_LSR, _dubins_RSL)]
    segs = [s for s in segs if s is not None]
    best = min(segs, key=lambda s: s[4])
    types, t_norm, p_norm, q_norm, _ = best

    # Convert normalised arc lengths to metres
    L1 = t_norm * rho
    L2 = p_norm * rho
    L3 = q_norm * rho
    total = L1 + L2 + L3

    n = max(2, int(total / step))
    configs = []

    for i in range(n+1):
        s_m = (i / n) * total   # arc length in metres
        x, y, h = q0

        # segment 1
        seg1 = min(s_m, L1)
        if L1 > 1e-6:
            x, y, h = _arc(x, y, h, rho, seg1, types[0]=="L")
        s_m -= seg1
        if s_m <= 1e-9:
            configs.append((x, y, h)); continue

        # segment 2 (straight)
        seg2 = min(s_m, L2)
        x += seg2 * math.cos(h)
        y += seg2 * math.sin(h)
        s_m -= seg2
        if s_m <= 1e-9:
            configs.append((x, y, h)); continue

        # segment 3
        x, y, h = _arc(x, y, h, rho, s_m, types[2]=="L")
        configs.append((x, y, h))

    return configs


# ==============================================================================
# Mission Simulator
# ==============================================================================

@dataclass
class Tel:
    """One telemetry sample."""
    t: float
    x: float; y: float; alt: float
    vx: float; vy: float; vz: float
    phi: float; theta: float; psi: float
    fw_rpm: float; fw_energy: float; fw_charge: float
    regen_w: float
    g_fl: float; g_fr: float
    tgt_x: float; tgt_y: float


class Mission:
    """Plans and simulates a full GyroDrone mission."""

    def __init__(
        self,
        waypoints: List[Tuple[float, float, float]],  # (x, y, heading_deg)
        altitude:  float = 10.0,
        speed:     float = 5.0,
        dt:        float = 0.01,
        regen:     bool  = True,
        wind_speed: float = 0.0,
        wind_dir:   float = 0.0,
        gust_sigma: float = None,
        noise:      bool  = False,
        seed:       int   = 42,
    ):
        self.wps      = waypoints
        self.alt      = altitude
        self.speed    = speed
        self.dt       = dt
        self.tel: List[Tel] = []
        rng   = np.random.default_rng(seed)
        wind  = Wind(rng, wind_speed, wind_dir, gust_sigma) if wind_speed > 0 or gust_sigma else None
        sens  = SensorNoise(rng) if noise else None
        self.wind_speed = wind_speed
        self.wind_dir   = wind_dir
        self.noise      = noise
        self.drone    = Dynamics(alt0=altitude, regen=regen, wind=wind, noise=sens)

    def _rho(self) -> float:
        """Momentum-aware minimum turning radius."""
        charge = self.drone.fw.charge
        r_min  = self.speed**2 / (G * math.tan(math.radians(30)))  # ~4.4m at 5m/s
        r_max  = r_min * 2.0
        # High charge -> tighter turns allowed (more gyroscopic stability budget)
        return r_max - (r_max - r_min) * charge

    def _build_path(self) -> List[Tuple[float, float, float]]:
        full = []
        rho  = self._rho()
        for i in range(len(self.wps)-1):
            wp0, wp1 = self.wps[i], self.wps[i+1]
            q0 = (wp0[0], wp0[1], math.radians(wp0[2]))
            q1 = (wp1[0], wp1[1], math.radians(wp1[2]))
            full.extend(dubins_sample(q0, q1, rho, step=1.5))
        return full

    def run(self) -> None:
        regen_str = "enabled" if self.drone.fw.regen else "disabled"
        print(f"\n{'='*58}", flush=True)
        print(f"GyroDrone Mission Simulation", flush=True)
        print(f"  Waypoints   : {len(self.wps)}", flush=True)
        print(f"  Altitude    : {self.alt} m", flush=True)
        print(f"  Speed       : {self.speed} m/s", flush=True)
        print(f"  Timestep    : {self.dt} s", flush=True)
        print(f"  Regen FESS  : {regen_str}", flush=True)
        if self.drone.wind:
            print(f"  Wind        : {self.wind_speed:.1f} m/s toward {self.wind_dir:.0f} deg "
                  f"(gust sigma {self.drone.wind.gust_sigma:.1f} m/s)", flush=True)
        print(f"  Sensor noise: {'on' if self.noise else 'off (perfect state)'}", flush=True)
        print(f"  Drone mass  : {MASS:.3f} kg", flush=True)
        print(f"  Hover omega : {OMEGA_HOVER:.0f} rad/s  ({OMEGA_HOVER*60/(2*math.pi):.0f} RPM)", flush=True)
        print(f"  I_zz        : {I_ZZ*1e4:.2f}e-4 kg*m^2", flush=True)
        print(f"{'='*58}\n", flush=True)

        path = self._build_path()
        rho  = self._rho()
        print(f"Dubins path: {len(path)} points, rho={rho:.2f} m\n", flush=True)

        t = 0.0
        s = self.drone.s

        for idx, (tx, ty, th) in enumerate(path):
            # Fixed time budget: 0.3s per path point (drone moves ~1.5m at 5m/s)
            steps = max(1, int(0.3 / self.dt))

            for _ in range(steps):
                self.drone.step(self.dt, tx, ty, self.alt, th)
                t += self.dt

                self.tel.append(Tel(
                    t=t, x=s.x, y=s.y, alt=s.alt,
                    vx=s.vx, vy=s.vy, vz=s.vz,
                    phi=s.phi, theta=s.theta, psi=s.psi,
                    fw_rpm=self.drone.fw.rpm,
                    fw_energy=self.drone.fw.energy,
                    fw_charge=self.drone.fw.charge,
                    regen_w=self.drone.fw.regen_power,
                    g_fl=self.drone.gimbal.fl,
                    g_fr=self.drone.gimbal.fr,
                    tgt_x=tx, tgt_y=ty,
                ))

            # Progress every 10% of path
            if idx % max(1, len(path)//10) == 0:
                print(
                    f"  t={t:6.1f}s  ({s.x:6.1f},{s.y:6.1f})  "
                    f"alt={s.alt:5.1f}m  "
                    f"spd={s.speed_2d:.1f}m/s  "
                    f"fw={self.drone.fw.rpm:5.0f}RPM  "
                    f"regen={self.drone.fw.regen_power:.1f}W",
                    flush=True,
                )

        total_regen = sum(r.regen_w * self.dt for r in self.tel)
        # Tracking quality: distance to current path target (target leads the
        # drone by design, so compare runs with the same mission/speed)
        offsets  = [math.hypot(r.x - r.tgt_x, r.y - r.tgt_y) for r in self.tel]
        alt_errs = [abs(r.alt - self.alt) for r in self.tel]
        print(f"\n{'='*58}", flush=True)
        print(f"Mission done:  t={t:.1f}s  |  {len(self.tel)} samples", flush=True)
        print(f"  Regen recovered  : {total_regen:.1f} J  ({total_regen/3600:.4f} Wh)", flush=True)
        print(f"  Final FW charge  : {self.drone.fw.charge:.0%}", flush=True)
        print(f"  Max 2D speed     : {max(math.sqrt(r.vx**2+r.vy**2) for r in self.tel):.1f} m/s", flush=True)
        print(f"  Target offset    : mean {sum(offsets)/len(offsets):.2f} m  "
              f"max {max(offsets):.2f} m", flush=True)
        print(f"  Altitude error   : mean {sum(alt_errs)/len(alt_errs):.2f} m  "
              f"max {max(alt_errs):.2f} m", flush=True)
        print(f"  Final pos        : ({s.x:.1f}, {s.y:.1f})", flush=True)
        print(f"{'='*58}\n", flush=True)


# ==============================================================================
# Visualization
# ==============================================================================

def plot(sim: Mission) -> None:
    tel = sim.tel
    if not tel:
        print("No telemetry to plot.", flush=True)
        return

    def arr(f): return np.array([f(r) for r in tel])

    t        = arr(lambda r: r.t)
    xs       = arr(lambda r: r.x)
    ys       = arr(lambda r: r.y)
    alts     = arr(lambda r: r.alt)
    fw_rpm   = arr(lambda r: r.fw_rpm)
    fw_e     = arr(lambda r: r.fw_energy)
    fw_c     = arr(lambda r: r.fw_charge)
    regen    = arr(lambda r: r.regen_w)
    g_fl     = np.degrees(arr(lambda r: r.g_fl))
    g_fr     = np.degrees(arr(lambda r: r.g_fr))
    roll_d   = np.degrees(arr(lambda r: r.phi))
    pitch_d  = np.degrees(arr(lambda r: r.theta))
    yaw_d    = np.degrees(arr(lambda r: r.psi))
    spd      = arr(lambda r: math.sqrt(r.vx**2 + r.vy**2))

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle("GyroDrone -- Full Physics Simulation", fontsize=14, fontweight="bold")
    gs  = GridSpec(3, 3, figure=fig, hspace=0.48, wspace=0.38)

    # -- Trajectory (top-down) --
    ax = fig.add_subplot(gs[:2, 0])
    sc = ax.scatter(xs, ys, c=fw_c, cmap="RdYlGn", s=2, vmin=0, vmax=1)
    plt.colorbar(sc, ax=ax, label="FW charge")
    for i, (wx, wy, _) in enumerate(sim.wps):
        ax.plot(wx, wy, "b^", ms=9, zorder=5)
        ax.annotate(f"WP{i}", (wx, wy), textcoords="offset points",
                    xytext=(5, 5), fontsize=8)
    step_a = max(1, len(tel)//40)
    for r in tel[::step_a]:
        ax.annotate("", xy=(r.x + 0.8*math.cos(r.psi), r.y + 0.8*math.sin(r.psi)),
                    xytext=(r.x, r.y),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=0.7))
    ax.set_title("Trajectory (color = FW charge)")
    ax.set_xlabel("X (m)"); ax.set_ylabel("Y (m)")
    ax.set_aspect("equal"); ax.grid(True, alpha=0.3)

    # -- Altitude --
    ax = fig.add_subplot(gs[2, 0])
    ax.plot(t, alts, color="steelblue", lw=1.2)
    ax.axhline(sim.alt, color="gray", ls="--", alpha=0.6, label="Target")
    ax.set_xlabel("Time (s)"); ax.set_ylabel("Alt (m)")
    ax.set_title("Altitude"); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # -- Flywheel RPM & energy --
    ax = fig.add_subplot(gs[0, 1])
    ax.plot(t, fw_rpm, color="darkorange", lw=1.2, label="RPM")
    ax.axhline(FW_RPM_MAX, color="red",  ls="--", alpha=0.4, label="Max")
    ax.axhline(FW_RPM_MIN, color="blue", ls="--", alpha=0.4, label="Min")
    ax2 = ax.twinx()
    ax2.plot(t, fw_e, color="purple", lw=1.0, alpha=0.7)
    ax2.set_ylabel("Energy (J)", color="purple")
    ax.set_ylabel("RPM", color="darkorange")
    ax.set_title("Flywheel RPM & Energy")
    ax.legend(fontsize=7, loc="upper left"); ax.grid(True, alpha=0.3)

    # -- Regen power --
    ax = fig.add_subplot(gs[1, 1])
    ax.fill_between(t, regen, alpha=0.5, color="limegreen")
    ax.plot(t, regen, color="green", lw=0.8)
    cum = np.cumsum(regen) * sim.dt
    ax2 = ax.twinx()
    ax2.plot(t, cum, color="darkgreen", lw=1.2, ls="--")
    ax2.set_ylabel("Cumul. (J)", color="darkgreen")
    ax.set_ylabel("Regen (W)"); ax.set_title("Regenerative Recovery"); ax.grid(True, alpha=0.3)

    # -- Gimbals --
    ax = fig.add_subplot(gs[2, 1])
    ax.plot(t, g_fl, lw=1.2, label="FL")
    ax.plot(t, g_fr, lw=1.2, ls="--", label="FR")
    ax.axhline(+15, color="red", ls=":", alpha=0.4)
    ax.axhline(-15, color="red", ls=":", alpha=0.4)
    ax.set_xlabel("Time (s)"); ax.set_ylabel("deg")
    ax.set_title("Gimbal Angles"); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # -- Roll & Pitch --
    ax = fig.add_subplot(gs[0, 2])
    ax.plot(t, roll_d,  lw=1.0, label="Roll")
    ax.plot(t, pitch_d, lw=1.0, label="Pitch")
    ax.set_ylabel("deg"); ax.set_title("Roll & Pitch")
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # -- Yaw --
    ax = fig.add_subplot(gs[1, 2])
    ax.plot(t, yaw_d, color="chocolate", lw=1.1)
    ax.set_ylabel("Yaw (deg)"); ax.set_title("Yaw Heading"); ax.grid(True, alpha=0.3)

    # -- Ground speed --
    ax = fig.add_subplot(gs[2, 2])
    ax.plot(t, spd, color="navy", lw=1.1)
    ax.axhline(sim.speed, color="gray", ls="--", alpha=0.6, label="Target")
    ax.set_xlabel("Time (s)"); ax.set_ylabel("m/s")
    ax.set_title("Ground Speed"); ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    plt.savefig("gyrodrone_simulation.png", dpi=150, bbox_inches="tight")
    print("Saved: gyrodrone_simulation.png", flush=True)
    plt.show()


# ==============================================================================
# Preset missions
# ==============================================================================

MISSIONS = {
    "circuit": [
        ( 0,  0,   0),
        (20,  0,  90),
        (20, 20, 180),
        ( 0, 20, 270),
        ( 0,  0,   0),
    ],
    "square": [
        ( 0,  0,  45),
        (25,  0,  90),
        (25, 25, 180),
        ( 0, 25, 270),
        ( 0,  0,  45),
    ],
    "figure8": [
        ( 0,  0,   0),
        (15, 10,  90),
        ( 0, 20, 180),
        (-15, 10, 270),
        ( 0,  0,   0),
        (15,-10,  90),
        ( 0,-20, 180),
        (-15,-10, 270),
        ( 0,  0,   0),
    ],
    "lawnmower": [
        ( 0,  0,   0),
        (30,  0,  90),
        (30, 10, 180),
        ( 0, 10, 270),
        ( 0, 20,   0),
        (30, 20,  90),
    ],
}


# ==============================================================================
# Entry point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="GyroDrone Physics Simulation")
    parser.add_argument("--mission",  default="circuit", choices=list(MISSIONS))
    parser.add_argument("--altitude", default=10.0, type=float)
    parser.add_argument("--speed",    default=5.0,  type=float)
    parser.add_argument("--dt",       default=0.01, type=float)
    parser.add_argument("--no-regen", action="store_true")
    parser.add_argument("--no-plot",  action="store_true")
    parser.add_argument("--wind",     default=0.0, type=float,
                        help="steady wind speed m/s")
    parser.add_argument("--wind-dir", default=90.0, type=float,
                        help="wind direction deg (blowing toward, NED heading)")
    parser.add_argument("--gust",     default=None, type=float,
                        help="gust sigma m/s (default 0.3*wind)")
    parser.add_argument("--noise",    action="store_true",
                        help="enable sensor noise (GPS bias, IMU/attitude noise)")
    parser.add_argument("--seed",     default=42, type=int)
    args = parser.parse_args()

    sim = Mission(
        waypoints = MISSIONS[args.mission],
        altitude  = args.altitude,
        speed     = args.speed,
        dt        = args.dt,
        regen     = not args.no_regen,
        wind_speed = args.wind,
        wind_dir   = args.wind_dir,
        gust_sigma = args.gust,
        noise      = args.noise,
        seed       = args.seed,
    )
    sim.run()

    if not args.no_plot:
        plot(sim)


if __name__ == "__main__":
    main()

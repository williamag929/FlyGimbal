#!/usr/bin/env python3
"""
FlyGimbal — ArduPilot flywheel feed-forward patch applier
src/firmware-patch/apply_patch.py

Applies the flywheel gyroscopic feed-forward patch to an ArduPilot tree:

  1. AC_AttitudeControl.h        — set_flywheel_momentum() setter + state
  2. AC_AttitudeControl_Multi.cpp — feed-forward term in the 400Hz rate loop
  3. bindings.desc                — Lua binding so the FWC applet can feed it

Physics (validated in src/simulation/gyrodrone_sim.py):
  flywheel H = [0, 0, H_z] in body frame; coupling torque on airframe is
  (-H_z*q, +H_z*p, 0). Cancellation feed-forward: tau_roll += H_z*q,
  tau_pitch -= H_z*p, converted to normalized actuator via act_per_nm.

Usage:
  python3 apply_patch.py /path/to/ardupilot
  python3 apply_patch.py /path/to/ardupilot --revert   (via git checkout)
"""

import sys
from pathlib import Path

EDITS = [
    # ── 1. Header: setter + members ──────────────────────────────────────
    (
        "libraries/AC_AttitudeControl/AC_AttitudeControl.h",
        "    void actuator_yaw_sysid(float command) { _actuator_sysid.z = command; }",
        """    void actuator_yaw_sysid(float command) { _actuator_sysid.z = command; }

    // FlyGimbal: gyroscopic feed-forward for an onboard flywheel (spin axis = body Z).
    // h_z_nms: flywheel angular momentum (N*m*s, signed by spin direction)
    // act_per_nm: normalized actuator output per N*m of body torque
    // Expires after 3s without refresh (see rate_controller_run_dt).
    void set_flywheel_momentum(float h_z_nms, float act_per_nm) {
        _flywheel_h_z = h_z_nms;
        _flywheel_act_per_nm = act_per_nm;
        _flywheel_update_ms = AP_HAL::millis();
    }""",
    ),
    (
        "libraries/AC_AttitudeControl/AC_AttitudeControl.h",
        "    Vector3f            _actuator_sysid;",
        """    Vector3f            _actuator_sysid;

    // FlyGimbal flywheel feed-forward state (see set_flywheel_momentum)
    float               _flywheel_h_z;
    float               _flywheel_act_per_nm;
    uint32_t            _flywheel_update_ms;""",
    ),
    # ── 2. Rate loop: feed-forward term ──────────────────────────────────
    (
        "libraries/AC_AttitudeControl/AC_AttitudeControl_Multi.cpp",
        """    _motors.set_roll(get_rate_roll_pid().update_all(ang_vel_body.x, gyro_rads.x,  dt, _motors.limit.roll, _pd_scale.x, _i_scale.x) + _actuator_sysid.x);
    _motors.set_roll_ff(get_rate_roll_pid().get_ff());

    _motors.set_pitch(get_rate_pitch_pid().update_all(ang_vel_body.y, gyro_rads.y,  dt, _motors.limit.pitch, _pd_scale.y, _i_scale.y) + _actuator_sysid.y);""",
        """    // FlyGimbal: cancel gyroscopic coupling from onboard flywheel (H = [0,0,Hz]).
    // Coupling torque on airframe is (-Hz*q, +Hz*p); feed-forward adds the negative.
    float fw_ff_roll = 0.0f;
    float fw_ff_pitch = 0.0f;
    if (!is_zero(_flywheel_h_z) && (AP_HAL::millis() - _flywheel_update_ms) < 3000) {
        fw_ff_roll  =  _flywheel_h_z * gyro_rads.y * _flywheel_act_per_nm;
        fw_ff_pitch = -_flywheel_h_z * gyro_rads.x * _flywheel_act_per_nm;
    }

    _motors.set_roll(get_rate_roll_pid().update_all(ang_vel_body.x, gyro_rads.x,  dt, _motors.limit.roll, _pd_scale.x, _i_scale.x) + _actuator_sysid.x + fw_ff_roll);
    _motors.set_roll_ff(get_rate_roll_pid().get_ff());

    _motors.set_pitch(get_rate_pitch_pid().update_all(ang_vel_body.y, gyro_rads.y,  dt, _motors.limit.pitch, _pd_scale.y, _i_scale.y) + _actuator_sysid.y + fw_ff_pitch);""",
    ),
    # ── 3. Lua binding ───────────────────────────────────────────────────
    (
        "libraries/AP_Scripting/generator/description/bindings.desc",
        "singleton AC_AttitudeControl method get_att_error_angle_deg float",
        """singleton AC_AttitudeControl method get_att_error_angle_deg float
singleton AC_AttitudeControl method set_flywheel_momentum void float -10 10 float 0 100""",
    ),
]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1])
    if not (root / "libraries/AC_AttitudeControl").is_dir():
        sys.exit(f"not an ArduPilot tree: {root}")

    for rel, old, new in EDITS:
        p = root / rel
        text = p.read_text()
        if new in text:
            print(f"  [skip] {rel} (already patched)")
            continue
        if old not in text:
            sys.exit(f"  [FAIL] anchor not found in {rel} — upstream changed, "
                     f"re-derive the patch.\n  anchor: {old.splitlines()[0]}")
        p.write_text(text.replace(old, new, 1))
        print(f"  [ok]   {rel}")

    print("Patch applied. Build SITL with: ./waf configure --board sitl && ./waf copter")


if __name__ == "__main__":
    main()

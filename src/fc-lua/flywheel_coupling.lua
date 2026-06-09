--[[
FlyGimbal — Flywheel Coupling Compensation (ArduPilot Lua applet)
src/fc-lua/flywheel_coupling.lua

Runs on the flight controller (ArduCopter 4.5+, SCR_ENABLE=1, file in
APM/scripts/). The companion computer broadcasts flywheel RPM as a
NAMED_VALUE_FLOAT named "FWRPM" (see momentum_manager.py).

What this does:
  1. Receives live flywheel RPM over MAVLink
  2. Gain-schedules ATC_RAT_RLL/PIT P+D with RPM — higher gyroscopic
     coupling torque needs stiffer disturbance rejection
  3. Logs flywheel state to dataflash (FWC log message)
  4. Warns the GCS on flywheel overspeed
  5. Reverts gains to baseline if RPM telemetry goes stale (failsafe)

What this CANNOT do (Lua API limitation):
  True gyroscopic feed-forward (tau_roll += L_fw*q, tau_pitch -= L_fw*p)
  requires injecting torque into the rate loop, which scripting does not
  expose. That needs a small AC_AttitudeControl firmware patch before
  sustained high-RPM flight. This applet is the interim mitigation.

Parameters created (FWC_):
  FWC_ENABLE    0=off, 1=monitor only, 2=monitor + gain scheduling
  FWC_RPM_MAX   flywheel RPM at full charge        (default 20000)
  FWC_SCL_MAX   gain multiplier at RPM_MAX         (default 1.25)
  FWC_RPM_WARN  GCS warning threshold              (default 19000)
--]]

local MAV_SEVERITY_WARNING = 4
local MAV_SEVERITY_INFO    = 6
local NAMED_VALUE_FLOAT_ID = 251
local RPM_TIMEOUT_MS       = 3000
local LOOP_MS              = 100

-- ── Parameters ───────────────────────────────────────────────────────────────

local PARAM_TABLE_KEY = 73
assert(param:add_table(PARAM_TABLE_KEY, "FWC_", 4), "FWC: param table failed")
assert(param:add_param(PARAM_TABLE_KEY, 1, "ENABLE",   2),     "FWC: param failed")
assert(param:add_param(PARAM_TABLE_KEY, 2, "RPM_MAX",  20000), "FWC: param failed")
assert(param:add_param(PARAM_TABLE_KEY, 3, "SCL_MAX",  1.25),  "FWC: param failed")
assert(param:add_param(PARAM_TABLE_KEY, 4, "RPM_WARN", 19000), "FWC: param failed")

local FWC_ENABLE   = Parameter("FWC_ENABLE")
local FWC_RPM_MAX  = Parameter("FWC_RPM_MAX")
local FWC_SCL_MAX  = Parameter("FWC_SCL_MAX")
local FWC_RPM_WARN = Parameter("FWC_RPM_WARN")

-- rate-controller gains we schedule, with boot-time baselines
local gains = {}
for _, name in ipairs({"ATC_RAT_RLL_P", "ATC_RAT_RLL_D",
                       "ATC_RAT_PIT_P", "ATC_RAT_PIT_D"}) do
  local p = Parameter(name)
  gains[#gains+1] = { p = p, base = p:get() }
end

-- ── MAVLink receive ──────────────────────────────────────────────────────────

mavlink:init(10, 1)
mavlink:register_rx_msgid(NAMED_VALUE_FLOAT_ID)

-- receive_chan() delivers a serialized mavlink_message_t struct:
--   checksum u16 @1 | magic @3 | len @4 | flags @5-6 | seq/sys/comp @7-9
--   | msgid u24 @10 | payload @13   (same layout for MAVLink 1 and 2)
-- NAMED_VALUE_FLOAT payload: time_boot_ms u32 | value f32 | name char[10]
local function parse_fwrpm(msg)
  local magic = string.unpack("<B", msg, 3)
  if magic ~= 0xFD and magic ~= 0xFE then return nil end
  local msgid = string.unpack("<I3", msg, 10)
  if msgid ~= NAMED_VALUE_FLOAT_ID then return nil end
  local payload = string.sub(msg, 13)
  if #payload < 18 then                      -- MAVLink2 zero-truncation
    payload = payload .. string.rep("\0", 18 - #payload)
  end
  local _, value = string.unpack("<I4f", payload)
  local name = string.sub(payload, 9, 18):gsub("%z", "")
  if name ~= "FWRPM" then return nil end
  return value
end

-- ── State ────────────────────────────────────────────────────────────────────

local rpm           = 0
local last_rpm_ms   = uint32_t(0)
local cur_scale     = 1.0
local warned_speed  = false
local warned_stale  = false
local have_telem    = false

local function apply_scale(scale)
  if scale == cur_scale then return end
  for _, g in ipairs(gains) do
    g.p:set(g.base * scale)                  -- runtime only, not saved
  end
  cur_scale = scale
end

-- ── Main loop ────────────────────────────────────────────────────────────────

local function update()
  -- drain received messages
  local msg = mavlink:receive_chan()
  while msg do
    local v = parse_fwrpm(msg)
    if v then
      rpm = v
      last_rpm_ms = millis()
      if not have_telem then
        have_telem = true
        gcs:send_text(MAV_SEVERITY_INFO, "FWC: flywheel telemetry online")
      end
      warned_stale = false
    end
    msg = mavlink:receive_chan()
  end

  local enable = FWC_ENABLE:get()
  if enable == 0 then
    apply_scale(1.0)
    return update, LOOP_MS
  end

  local stale = have_telem and (millis() - last_rpm_ms) > RPM_TIMEOUT_MS

  -- overspeed warning
  if rpm > FWC_RPM_WARN:get() and not warned_speed then
    gcs:send_text(MAV_SEVERITY_WARNING,
                  string.format("FWC: flywheel overspeed %.0f RPM", rpm))
    warned_speed = true
  elseif rpm < FWC_RPM_WARN:get() * 0.95 then
    warned_speed = false
  end

  -- stale telemetry failsafe: fall back to baseline gains
  if stale then
    if not warned_stale then
      gcs:send_text(MAV_SEVERITY_WARNING, "FWC: flywheel RPM stale, gains reverted")
      warned_stale = true
    end
    apply_scale(1.0)
    return update, LOOP_MS
  end

  -- gain scheduling
  if enable >= 2 and have_telem then
    local frac  = math.min(1.0, math.max(0.0, rpm / FWC_RPM_MAX:get()))
    local scale = 1.0 + (FWC_SCL_MAX:get() - 1.0) * frac
    apply_scale(scale)
  end

  logger:write("FWC", "RPM,Scl", "ff", rpm, cur_scale)
  return update, LOOP_MS
end

gcs:send_text(MAV_SEVERITY_INFO, "FWC: flywheel_coupling.lua loaded")
return update()

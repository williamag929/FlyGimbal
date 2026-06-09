#!/bin/bash
# FlyGimbal — build patched ArduCopter SITL (run inside WSL)
# Usage: bash /mnt/d/Projects/Python/FlyGimbal/src/firmware-patch/build_sitl.sh
set -e

AP=~/ardupilot
REPO=/mnt/d/Projects/Python/FlyGimbal

echo "=== applying FlyGimbal flywheel feed-forward patch ==="
python3 "$REPO/src/firmware-patch/apply_patch.py" "$AP"

echo "=== exporting patch file to repo ==="
git -C "$AP" diff > "$REPO/src/firmware-patch/flywheel_ff.patch"
wc -l "$REPO/src/firmware-patch/flywheel_ff.patch"

echo "=== waf configure (board: sitl) ==="
cd "$AP"
./waf configure --board sitl 2>&1 | tail -3

echo "=== waf copter (this takes 10-20 min) ==="
./waf copter 2>&1 | tail -5

echo "=== staging patched binary + lua script ==="
mkdir -p ~/sitl-patched/scripts
cp build/sitl/bin/arducopter ~/sitl-patched/
cp "$REPO/src/fc-lua/flywheel_coupling.lua" ~/sitl-patched/scripts/
cp ~/sitl/copter.parm ~/sitl-patched/ 2>/dev/null || \
  curl -sL -o ~/sitl-patched/copter.parm https://raw.githubusercontent.com/ArduPilot/ardupilot/master/Tools/autotest/default_params/copter.parm

echo "BUILD_OK — launch with:"
echo "  wsl -e bash -c 'cd ~/sitl-patched && rm -f eeprom.bin && exec ./arducopter -w --model + --speedup 2 --defaults copter.parm --home -35.363261,149.165230,584,353'"

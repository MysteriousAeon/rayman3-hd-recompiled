#!/bin/bash
# M23 (D-053): superseded visible-window pilot; unattended runs use m6_pilot_run.py (hidden runner) only.
if [ -z "$R3HD_LEGACY_VISIBLE_RUN" ]; then echo "Superseded runner (D-053): use tools/m6_pilot_run.py" >&2; exit 2; fi
# Closed-loop intro_10 run: normal menu schedule, then the read-only flight pilot.
# usage: bash tools/m5_pilot_run.sh RUN SECONDS [SCHEDULE]   (repository root, Git Bash)
# GROUND_ARGS, when set, runs tools/m5_ground_probe.py with those arguments after the pilot returns.
set -e
RUN=$1; TOTAL=${2:-420}; SCHEDULE=${3:-config/m5/idle.txt}
R=private/work/m5_runs/$RUN
powershell -NoProfile -ExecutionPolicy Bypass -File tools/run_milestone5.ps1 -Seconds $TOTAL -Run $RUN -Schedule $SCHEDULE -Follow > private/work/m5_$RUN.launch.log 2>&1 &
until grep -qs "intro_10.lvl result=00000000" $R/runtime*.log; do sleep 2; done
sleep 22   # opening in-engine cinematic; actors exist and the fly generator reaches NIN_C_FlyMvt
PID=$(tasklist | grep -i r3hd.exe | awk '{print $2}' | head -1)
BASE=$(grep -h "Guest memory arena mapped" $R/runtime*.log | head -1 | sed -E 's/.*virtual base 0x0*([0-9A-Fa-f]+),.*/\1/')
echo "pid=$PID base=$BASE"
python tools/m5_memory_probe.py $PID $BASE $R/actors.json --regions
python tools/m5_script_probe.py $PID $BASE $R/actors.json $R/scripts
python tools/m5_flight_pilot.py $PID $BASE $R/actors.json $R/schedule.txt $R/pilot.log --seconds ${PILOT_SECONDS:-200}
echo "pilot finished"
if [ -n "$GROUND_ARGS" ]; then python tools/m5_ground_probe.py $PID $BASE $R $GROUND_ARGS; fi

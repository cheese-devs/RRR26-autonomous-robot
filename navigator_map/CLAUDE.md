# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Autonomous Yahboomcar robot for the **RRR26 competition** (แข่งจริง 30-31 พ.ค. 2569 ที่ห้องไดมอนด์ฮอลล์ ชั้น 5 ศูนย์การค้าเซียร์รังสิต). Stack: ROS 2 Humble + Nav2 + AprilTag (tag36h11) + servo dispenser. Mission: visit the waypoints listed in `nav_waypoints.yaml`; at each one either dispense a relief box (**person** waypoint — known from the YAML `type`, no detection) or read an **AprilTag** ID, then return HOME. (MediaPipe pose detection was removed — see below.)

Format การแข่ง: รอบแรก 3 ครั้ง × 10 นาที (เอา 2 ครั้งดีสุดรวม), 2 ทีมคะแนนสูงสุดเข้ารอบชิง 1 รอบ. คะแนนเต็ม 260 (60 จากภารกิจ + 200 ซูเปอร์บิงโก). **กฎสำคัญ:** หุ่นไม่คืบหน้า >10 วินาที = กรรมการบังคับ retry (เสียโอกาสซูเปอร์บิงโก). ตำแหน่ง/รูปร่างผู้ประสบภัยและ AprilTag ID **ประกาศวันแข่ง + อาจเปลี่ยนระหว่างรอบ** — ต้องแก้ `nav_waypoints.yaml` ได้เร็วหน้างาน.

Working directory (`navigator_map/`) is the runtime project — it must be the CWD when launching, because `nav2_launch.py` uses relative paths (`my_robot_map.yaml`, `prarams/dwb_nav_params.yaml`, `rviz/...`).

Code, comments, and console output are in **Thai**. Match that style when editing — don't translate existing Thai to English.

## Running the system

```bash
./run_all_mission.sh          # launches 3 terminator windows: nav2_launch, Cam_Pose_AprilTag, navigator_script
```

`navigator_script.py` is **interactive** — it reads waypoint order from stdin, then `0` to exit. The order is 1-based indices into `nav_waypoints.yaml`; HOME is the **last** entry (index 6 with the current 5-waypoint map), so a full loop back home is `1,2,3,4,5,6` — `1,2,3,4,5` alone stops at waypoint_5 without returning HOME. For non-interactive runs pipe input:

```bash
printf '1,2,3,4,5,6\n0\n' | python3 navigator_script.py
```

Individual processes for debugging:
```bash
ros2 launch nav2_launch.py            # Nav2 stack only
python3 Cam_Pose_AprilTag.py          # vision node only
python3 mission_script.py person      # or 'tag' — mission_script is normally a subprocess
python3 get_waypoint.py               # record waypoints from current TF (press 's' to save)
```

Live diagnostics while Nav2 runs: `bash diag.sh 2>&1 | tee diag_out.txt` — checks `/scan`, `/odom`, `/tf` rates and TF chains, used when "Extrapolation Error" appears.

## Architecture — 3-process flow

```
run_all_mission.sh
├─ nav2_launch.py            : RViz2 → yahboomcar_bringup → Nav2 (AMCL+costmaps+planners) → static TF base_link→laser_frame
├─ Cam_Pose_AprilTag.py      : runs throughout. /espRos/esp32camera → AprilTag (tag36h11) → /vision/latest_at_id (gated by /vision/detect_enable)
└─ navigator_script.py       : waits for Nav2 active, prompts user, drives waypoints
       │
       └─ on SUCCEEDED (non-HOME) → subprocess: python3 mission_script.py <type>   (blocking)
```

**Detection gate (`/vision/detect_enable` Bool):** the vision node runs **only AprilTag** and defaults OFF to save CPU. `navigator_script` enables it (`set_detect(True)`, then `False` in a `finally`) **only at tag waypoints** — person waypoints never touch the camera, so MediaPipe was removed entirely and `/mediapipe/points` no longer exists.

**Mission flow inside `mission_script.py`:** argv is `person` or `tag`.
- **person** → dispenses immediately via a 0.05s timer (`_person_drop_immediately`), **no camera, no detection**. The YAML already marks the waypoint as a person; the rules score "box in the red frame", not "detected a human first" — this removes MediaPipe-miss risk and the >10s spin that triggers a referee restart.
- **tag** → subscribes `/vision/latest_at_id`. `_check_link` polls until the publisher is discovered (DDS race) or `LINK_TIMEOUT_SEC` (3.0s). Then a `WARMUP_SEC` (2.5s) stationary scan collects a vote every frame and decides by `Counter.most_common` if ≥`WARMUP_VOTE_MIN`=3 frames; otherwise it spins at `ROTATE_SPEED` (0.15 rad/s) collecting more until `SPIN_VOTE_MIN`=10. `MISSION_TIMEOUT_SEC` (11.0s) hard-caps the whole mission — on timeout it stops the wheels, emits the best vote so far (if any), and exits, to stay under the referee's 10s rule.

**Servo dispense (`_drop_servo`, person only):** wait for a `/servo_s1` subscriber (≤`SERVO_LINK_SEC`=3s), then a **2-strike** sequence: pre-load `+89` (0.7s) → `-89` (0.6s, strike 1) → `+89` (0.6s) → `-89` (0.6s, strike 2) → `0` (0.3s). Each angle is re-published every 0.1s (a single publish can be lost to DDS discovery race). Two strikes drop 2 boxes per waypoint as a safety margin.

**Waypoint flow inside `navigator_script.py`:**
- Each waypoint may have an optional `via:` list — intermediate poses driven through *without* a mission. Used for `waypoint_3` (via `(2.65, 0.05)`) to force an upper-route path that avoids the narrow `⊐`-box corridor where the planner oscillated.
- `_goto_pose()` calls `clearAllCostmaps()` before every navigation (rinses "ghost" obstacles from mislocalization drift), then sleeps `CLEAR_SETTLE_SEC`=1.0s, then `goToPose`. On FAILED it retries up to `MAX_NAV_RETRY`=1 time.
- HOME is a special case — no mission, just sleep 2s.
- `emergency_stop()` (SIGTERM handler + `finally`) cancels the Nav2 task and publishes zero `/cmd_vel` ×5. **Always do this before killing robot processes** — otherwise wheels keep spinning.

## Nav2 params — source of truth

`nav2_launch.py` loads **`prarams/dwb_nav_params.yaml`** (note misspelled directory). The file `prarams/rpp_nav_params.yaml` is **not loaded** — do not edit it expecting effect.

Robot footprint is a rectangle `[[0.10,0.08],[0.10,-0.08],[-0.10,-0.08],[-0.10,0.08]]` (0.20×0.16 m) + `footprint_padding: 0.03`. **Do not switch back to `robot_radius`** — the circular approximation (Ø0.28) makes the robot refuse to enter the ~0.60 m U-shaped pockets at wp1/wp4 and triggers recovery loops.

Other tuned values: `xy_goal_tolerance: 0.15`, `yaw_goal_tolerance: 0.15`, `inflation_radius: 0.10` (both local + global), `use_rotate_to_heading: False` (kills mid-path "head shake" from AMCL noise), `max_vel_x: 0.20`.

## Map & AMCL

Map: `my_robot_map.pgm` (66×57 px, res 0.05, origin `(-0.342, -2.49, 0)`) → extent X[-0.34, 2.96], Y[-2.49, 0.36]. The y=0.36 top wall is real; `worldToMap failed` log spam from NavFn checking above the top row is harmless and not fixed by widening the map.

AMCL has `set_initial_pose: true` seeded at (0,0,0). **Hard rule:** physically place the robot at the start pose with yaw 0 (facing +x) before launching. If misplaced, AMCL relocalizes to wherever the laser scan matches best (observed jump to (1.98, -1.53) in run #7), then costmap paints walls over the robot and the first waypoint fails immediately.

## Mission outcome is *not* propagated

`navigator_script` prints `[SUCCESS]` based purely on `TaskResult.SUCCEEDED` from Nav2 — `mission_script` always exits 0, even when the servo never moved or no tag was read. When debugging "task succeeded but servo didn't fire", look at `mission_script` logs, not navigator output.

## Robot configs (sibling `start_up_robot/`)

One venue template `config_robot_RRR26.py` — edit SSID/password/agent-IP placeholders before each session (competition rules require the venue's 2.4 GHz WiFi). micro-ROS agent runs in Docker via `start_agent_computer.sh` (port 8090) / `start_Camera_computer.sh` (port 9999).

## Files reference

| File | Role |
|---|---|
| `nav2_launch.py` | Nav2 + bringup + RViz, loads `dwb_nav_params.yaml` |
| `navigator_script.py` | waypoint driver, calls mission_script per waypoint |
| `mission_script.py` | per-waypoint detector (person|tag), spawned as subprocess |
| `Cam_Pose_AprilTag.py` | vision node, gated by `/vision/detect_enable` |
| `nav_waypoints.yaml` | waypoints (x, y, orientation z/w, type, optional `via`) |
| `get_waypoint.py` | record waypoint from current `map→base_link` TF |
| `my_robot_map.{pgm,yaml}` | arena occupancy map |
| `prarams/dwb_nav_params.yaml` | the only Nav2 params file actually loaded |
| `diag.sh` | live ROS topic/TF health check |
| `docs/RRR26.pdf` | competition rules |
| `docs/KNOWLEDGE.md` | tutorial-style write-up of the whole pipeline |
| `docs/RACE_LESSONS_RRR26.md` | บทเรียนวันแข่งจริง (ผ่านทุกรอบ) + เช็กลิสต์ก่อนสตาร์ท |

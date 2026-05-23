# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Autonomous Yahboomcar robot for the **RRR26 competition** (deadline 29 พ.ค. 2026). Stack: ROS 2 Humble + Nav2 + MediaPipe pose + AprilTag (tag36h11) + servo drop. Mission: visit 5 waypoints, at each waypoint detect either a person (servo drop) or an AprilTag (read ID), then return HOME.

Working directory (`navigator_map/`) is the runtime project — it must be the CWD when launching, because `nav2_launch.py` uses relative paths (`my_robot_map.yaml`, `prarams/dwb_nav_params.yaml`, `rviz/...`).

Code, comments, and console output are in **Thai**. Match that style when editing — don't translate existing Thai to English.

## Running the system

```bash
./run_all_mission.sh          # launches 3 terminator windows: nav2_launch, Cam_Pose_AprilTag, navigator_script
```

`navigator_script.py` is **interactive** — it reads waypoint order from stdin (e.g. `1,2,3,4,5`, then `0` to exit). For non-interactive runs pipe input:

```bash
printf '1,2,3,4,5\n0\n' | python3 navigator_script.py
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
├─ Cam_Pose_AprilTag.py      : runs throughout. /espRos/esp32camera → MediaPipe + AprilTag → /mediapipe/points, /vision/latest_at_id
└─ navigator_script.py       : waits for Nav2 active, prompts user, drives waypoints
       │
       └─ on SUCCEEDED (non-HOME) → subprocess: python3 mission_script.py <type>   (blocking)
```

**Detection gate (`/vision/detect_enable` Bool):** vision node defaults OFF to save CPU during navigation. `navigator_script.set_detect(True)` before mission, `False` in `finally` after. `Cam_Pose_AprilTag` gates both MediaPipe and AprilTag on this flag.

**Mission flow inside `mission_script.py`:**
1. Argv decides which detector to subscribe to (`person` → `/mediapipe/points`, `tag` → `/vision/latest_at_id`). Subscribing to **only one** prevents the person detector from triggering a servo drop at a tag waypoint.
2. `_check_link` polls until the publisher is discovered (DDS race) or `LINK_TIMEOUT_SEC` (8s).
3. `WARMUP_SEC` (2.5s) stationary scan. Tag mode collects votes every frame, decides by `Counter.most_common` after warmup (≥`WARMUP_VOTE_MIN`=5 frames). Person mode triggers on first non-empty PointArray.
4. If nothing in warmup, robot spins at `ROTATE_SPEED` (0.15 rad/s) until found or votes reach `SPIN_VOTE_MIN`=10.
5. Servo drop sequence: wait for `/servo_s1` subscriber, then `_hold_servo(-90, 1.0s)` → `_hold_servo(0, 1.0s)`, re-publishing every 0.1s (single publish can be lost to DDS discovery race).

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

Map: `my_robot_map.pgm` (74×82 px, res 0.05, origin `(-0.358, -3.69, 0)`) → free area ≈ X[0, 2.95], Y[-2.45, 0.41]. The y=0.41 wall is real; `worldToMap failed` log spam from NavFn checking above the top row is harmless and not fixed by widening the map.

AMCL has `set_initial_pose: true` seeded at (0,0,0). **Hard rule:** physically place the robot at the start pose with yaw 0 (facing +x) before launching. If misplaced, AMCL relocalizes to wherever the laser scan matches best (observed jump to (1.98, -1.53) in run #7), then costmap paints walls over the robot and the first waypoint fails immediately.

## Mission outcome is *not* propagated

`navigator_script` prints `[SUCCESS]` based purely on `TaskResult.SUCCEEDED` from Nav2 — `mission_script` always exits 0, even when the servo never moved or no tag was read. When debugging "task succeeded but servo didn't fire", look at `mission_script` logs, not navigator output.

## Robot configs (sibling `start_up_robot/`)

Per-WiFi-network Python configs: `config_robot_RRR26.py`, `config_robot_RRR26.py`, `config_robot_RRR26.py`, `config_robot_RRR26.py`. Competition rules require the venue's 2.4 GHz WiFi — pick the matching config. micro-ROS agent runs in Docker via `start_agent_computer.sh` (port 8090) / `start_Camera_computer.sh` (port 9999).

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
| `RRR26.pdf` | competition rules (sibling: also at repo root) |

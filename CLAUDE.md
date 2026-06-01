# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Autonomous Yahboom 4-wheel robot for **RRR26 RoboRescue** (แข่ง 30-31 พ.ค. 2569 เซียร์รังสิต). Stack: ROS 2 Humble + Nav2 + slam_toolbox + MediaPipe pose + AprilTag (tag36h11) + servo dispenser. Robot does **not** run ROS 2 — it speaks micro-ROS (DDS-XRCE) over Wi-Fi UDP to a Docker agent on the host PC which bridges it into the ROS 2 graph.

Code, comments, prints, and commit messages are in **Thai**. Match that style — do not translate existing Thai to English.

This is **not a ROS package** — no `setup.py`/`package.xml`. Every script is run directly via `python3` or `ros2 launch` from inside its phase directory. Launch files use `os.path.abspath()` against CWD, so the working directory matters.

## 3-phase workflow (3 sibling directories)

Each phase lives in its own directory and **must be CWD** when launching:

| Phase | Dir | What it does |
|---|---|---|
| 1. Bring-up | `start_up_robot/` | Configure robot over USB-serial, start micro-ROS agents, manual teleop, watchdog |
| 2. SLAM | `slam_map/` | slam_toolbox online_async + drive to map, save `my_robot_map.{pgm,yaml}` |
| 3. Navigation | `navigator_map/` | Nav2 + waypoint mission + vision + servo drop (the runtime stack for race day) |

**Map handoff is manual:** copy `my_robot_map.pgm` + `my_robot_map.yaml` from `slam_map/` into `navigator_map/` after every mapping session. They are tracked in git in both locations.

## Common commands

### Phase 1 — bring-up
```bash
cd start_up_robot
./start_agent_computer.sh           # docker micro-ROS agent, port 8090 (robot base)
./start_Camera_computer.sh          # docker micro-ROS agent, port 9999 (ESP32 cam)
./check_robot.sh                    # 3 windows: cam viewer + teleop + vision check
python3 config_robot_<wifi>.py      # one-time over USB: SSID, agent IP, PID, domain id
python3 watchdog.py                 # real-time camera/IMU/battery status
```

### Phase 2 — SLAM
```bash
cd slam_map
./slam_map.sh                       # slam_toolbox + RViz
# (in another window) python3 ctrl_robot.py — drive around to fill the map
./save_map.sh                       # writes my_robot_map.{pgm,yaml} in CWD
# then: cp my_robot_map.* ../navigator_map/
```

### Phase 3 — navigation / mission
```bash
cd navigator_map
./run_all_mission.sh                # 3 terminator windows: nav2_launch + Cam_Pose_AprilTag + navigator_script
# OR individually:
ros2 launch nav2_launch.py          # Nav2 + bringup + RViz
python3 Cam_Pose_AprilTag.py        # vision node (gated by /vision/detect_enable)
python3 navigator_script.py         # interactive prompt: "1,2,3,4,5" then "0" to exit
python3 get_waypoint.py             # capture current TF pose into nav_waypoints.yaml
bash diag.sh 2>&1 | tee diag_out.txt  # live /scan //odom /tf health when "Extrapolation Error" appears
```

For Nav2-specific architecture (waypoint flow, mission_script gating, Nav2 params, AMCL hard rules, footprint vs `robot_radius` decision, `via:` waypoints, etc.) read **`navigator_map/CLAUDE.md`** — it is the source of truth for the runtime stack. `navigator_map/docs/KNOWLEDGE.md` has a deeper tutorial-style write-up of the whole pipeline; `navigator_map/docs/RRR26.pdf` holds the official rules.

## Per-WiFi robot configs

`start_up_robot/` has one `config_robot_*.py` per WiFi network the robot has been pre-flashed for: `config_robot_RRR26.py`, `config_robot_RRR26.py`, `config_robot_RRR26.py`, `config_robot_RRR26.py`. Competition requires the venue's 2.4 GHz WiFi — pick the matching config or write a new one (copy + edit SSID/password/agent IP). Domain ID must match between robot config and host `ROS_DOMAIN_ID` (default 99).

## Gotchas

1. **`prarams/` is intentionally misspelled** in `navigator_map/` and `slam_map/`. Launch files reference it by that spelling — don't rename one side without the other.
2. **Static TF `base_link → laser_frame`** is duplicated in `slam_map/map_slamtoolbox_launch.py` and `navigator_map/nav2_launch.py`. If lidar mounting changes, edit both.
3. **Stop the wheels before killing nav processes** — publish zero `/cmd_vel` (×5) first. `pkill` alone leaves wheels spinning because the last velocity command latches in the firmware. `navigator_script.emergency_stop()` already does this; one-off kills must too.
4. **brltty steals CH340 USB-serial** — if `/dev/ttyUSB0` doesn't appear when plugging in the robot, purge brltty fully: `sudo apt-get purge brltty`, remove `/usr/lib/udev/rules.d/85-brltty.rules`, and `pkill brltty`. Replug after.
5. **AMCL `set_initial_pose: true`** is required in `prarams/dwb_nav_params.yaml` — otherwise AMCL waits forever for an initial pose and the `map` frame is never published. Physically place the robot at (0,0) yaw=0 before launching Nav2; misplacement causes AMCL to relocalize to a wrong pocket and the first waypoint fails.
6. **Servo `/servo_s1` is pulse, not latch** — to drop: publish `-90` repeatedly every 0.1s for ~1.0s, then `0` repeatedly for ~1.0s. A single publish loses to DDS discovery race.

## Memory & competition context

There is an extensive auto-memory store under `~/.claude/projects/-home-pray-microROS-X-Example/memory/` (indexed by `MEMORY.md`, mirrored read-only in `memory_export/`). It holds: RRR26 rules summary, arena/survivor-zone layout, servo dispenser strategy, navigation debugging history, and per-incident feedback notes. Consult it for race-day rules, scoring, or past run failures before re-deriving from PDF or git log.

#!/bin/bash

# รันได้จาก path ไหนก็ได้ — cd เข้า directory ของสคริปต์เสมอ
cd "$(dirname "$0")" || exit 1

# Launch Navigation 2
terminator -u -e 'ros2 launch nav2_launch.py' &

# Launch Camera (runs throughout entire mission)
terminator -u -e 'python3 Cam_Pose_AprilTag.py' &

# Launch Mission Script
terminator -u -e 'python3 navigator_script.py' &

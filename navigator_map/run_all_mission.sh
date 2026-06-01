#!/bin/bash

# รันได้จาก path ไหนก็ได้ — cd เข้า directory ของสคริปต์เสมอ
cd "$(dirname "$0")" || exit 1

# ปิด RViz เป็น default (วันแข่ง — ลด CPU)
# ถ้าจะซ้อม/ดีบั๊ก localization (เช่นใช้ปุ่ม 2D Pose Estimate) ให้สั่ง: OPEN_RVIZ=true ./run_all_mission.sh
OPEN_RVIZ="${OPEN_RVIZ:-false}"

# Launch Navigation 2
terminator -u -e "bash -c \"ros2 launch nav2_launch.py open_rviz:=${OPEN_RVIZ} 2>&1 | tee /tmp/nav2.log\"" &

# Launch Camera (runs throughout entire mission)
terminator -u -e 'bash -c "python3 -u Cam_Pose_AprilTag.py 2>&1 | tee /tmp/vision.log"' &

# Launch Mission Script
terminator -u -e 'bash -c "python3 -u navigator_script.py 2>&1 | tee /tmp/navigator.log"' &

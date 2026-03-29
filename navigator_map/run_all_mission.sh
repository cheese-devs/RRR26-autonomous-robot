#!/bin/bash

# Launch Navigation 2
terminator -u -e 'ros2 launch nav2_launch.py' &

# Launch Mission Script (Fixed the double "python3")
terminator -u -e 'python3 navigator_script.py' &

# Launch AprilTag Tracking
terminator -u -e 'python3 Cam_Pose_AprilTag.py' &

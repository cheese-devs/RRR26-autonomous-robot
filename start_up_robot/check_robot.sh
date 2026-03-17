#!/bin/bash

# 1. open show camera
terminator -u -e "ros2 run yahboom_esp32_camera sub_img;exit" &
# 2. open ctrl_robot
terminator -u -e "python3 ctrl_robot.py;exit"&
# 3. open Chack Vision
terminator -u -e "python3 Cam_Pose_AprilTag.py;exit"&


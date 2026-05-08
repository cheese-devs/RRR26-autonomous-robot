#!/bin/bash

# Launch Navigation 2
terminator -u -e 'ros2 launch nav2_launch.py' &

# Launch Mission Script
terminator -u -e 'python3 navigator_script.py' &

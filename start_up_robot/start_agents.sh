#!/bin/bash

# 1. ชื่อ Container (เผื่อไว้สั่ง Stop)
NAME_1="uros_agent_8090"
NAME_2="uros_agent_9999"

# 2. ล้างตัวเก่าที่อาจค้างอยู่
echo "Cleaning up old agents..."
docker stop $NAME_1 $NAME_2 2>/dev/null
docker rm $NAME_1 $NAME_2 2>/dev/null

# 3. สั่งรัน Terminator พร้อม Layout ที่เราตั้งชื่อไว้
echo "Launching Terminator with Dual Agent Layout..."
terminator -l start_up &

echo "Agents are starting in a split window!"

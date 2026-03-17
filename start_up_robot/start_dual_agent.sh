#!/bin/bash

# 1. ชื่อ Container
NAME_1="uros_agent_8090"
NAME_2="uros_agent_9999"

# 2. ล้างตัวเก่าก่อนรันใหม่
docker stop $NAME_1 $NAME_2 2>/dev/null
docker rm $NAME_1 $NAME_2 2>/dev/null

# 3. สั่งรัน Terminator โดยใช้คำสั่ง -e (execute) 
# และใช้ --new-tab หรือการส่งคำสั่งเลเยอร์แบ่งหน้าจอ
# หมายเหตุ: เราจะใช้ Layout แบบแบ่งครึ่ง (Split)

terminator -u -e "docker run -it --rm --name $NAME_1 -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 8090 -v4" &

sleep 1 # รอให้ตัวแรกขึ้นก่อนเล็กน้อย

# สั่งตัวที่สองเปิดในหน้าต่างเดิมแต่แบ่งคนละส่วน (หรือเปิดหน้าต่างใหม่ถ้าไม่ได้ตั้ง Layout ไว้)
terminator -u -e "docker run -it --rm --name $NAME_2 -v /dev:/dev -v /dev/shm:/dev/shm --privileged --net=host microros/micro-ros-agent:humble udp4 --port 9999 -v4" &

echo "Terminator windows started for both agents."

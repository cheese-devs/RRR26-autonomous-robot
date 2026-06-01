#!/bin/bash

# 1. กำหนดชื่อ Container ให้เรียกง่าย
CONTAINER_NAME="uros_agent_9999"

# 2. ดัก Ctrl+C ให้ปิด container แล้วออกจาก loop จริง ๆ
cleanup() {
    echo ""
    echo ">>> ได้รับ Ctrl+C — กำลังหยุด agent..."
    docker stop $CONTAINER_NAME 2>/dev/null
    docker rm $CONTAINER_NAME 2>/dev/null
    exit 0
}
trap cleanup INT TERM

# 3. Loop รัน agent — ถ้า crash (BadParamException จาก fragment เสีย) จะรันใหม่อัตโนมัติ
while true; do
    echo "Cleaning up old container..."
    docker stop $CONTAINER_NAME 2>/dev/null
    docker rm $CONTAINER_NAME 2>/dev/null

    echo "Starting Micro-ROS Agent..."
    docker run -it --rm \
      --name $CONTAINER_NAME \
      -v /dev:/dev \
      -v /dev/shm:/dev/shm \
      --privileged \
      --net=host \
      microros/micro-ros-agent:humble udp4 --port 9999 -v4

    echo ""
    echo ">>> agent ตายหรือออก — รีสตาร์ทใน 2 วิ (กด Ctrl+C เพื่อหยุดถาวร)"
    sleep 2
done

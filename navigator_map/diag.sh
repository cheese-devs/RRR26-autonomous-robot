#!/bin/bash
# diag.sh — เก็บข้อมูลวินิจฉัยตอน nav2 รันสด (ใช้ตอนเจอ Extrapolation Error)
#
# วิธีใช้:
#   1) รัน ./run_all_mission.sh ตามปกติ
#   2) รอ ~30-40 วินาที จนหน้าต่าง nav2 เริ่มพ่น "Extrapolation Error" รัวๆ
#   3) เปิด terminal ใหม่ แล้วรัน:  bash diag.sh 2>&1 | tee diag_out.txt
#   4) ส่งไฟล์ diag_out.txt (หรือก๊อปผลทั้งหมด) ให้ Claude

source /opt/ros/humble/setup.bash 2>/dev/null

line() { echo; echo "================ $1 ================"; }

line "0) เวลาระบบตอนเริ่มเช็ค (epoch)"
date +%s.%N

line "1) NODES ที่กำลังรันอยู่"
ros2 node list

line "2) อัตราส่ง /scan  (lidar — ควรได้สม่ำเสมอ ~5-15 Hz)"
timeout 5 ros2 topic hz /scan || echo "[!] /scan ไม่มีข้อมูล — lidar ไม่ทำงาน"

line "3) อัตราส่ง /odom"
timeout 5 ros2 topic hz /odom || echo "[!] /odom ไม่มีข้อมูล"

line "4) อัตราส่ง /tf"
timeout 5 ros2 topic hz /tf || echo "[!] /tf ไม่มีข้อมูล"

line "5) /scan header.stamp — เช็คว่าค้างไหม (อ่าน 2 ครั้ง ห่าง 2 วิ)"
echo "-- ครั้งที่ 1 --"
timeout 4 ros2 topic echo /scan --field header.stamp --once
sleep 2
echo "-- ครั้งที่ 2 (ถ้าเลข sec/nanosec เท่าเดิม = /scan ค้าง = ต้นเหตุ) --"
timeout 4 ros2 topic echo /scan --field header.stamp --once

line "6) /odom header.stamp — เช็คว่าค้างไหม"
echo "-- ครั้งที่ 1 --"
timeout 4 ros2 topic echo /odom --field header.stamp --once
sleep 2
echo "-- ครั้งที่ 2 --"
timeout 4 ros2 topic echo /odom --field header.stamp --once

line "7) TF map -> base_link  (ดูบรรทัด 'At time ...' ว่าเดินไหม)"
timeout 4 ros2 run tf2_ros tf2_echo map base_link

line "8) TF odom -> base_link  (มาจาก EKF)"
timeout 4 ros2 run tf2_ros tf2_echo odom base_link

line "9) เวลาระบบตอนจบเช็ค (epoch) — เทียบกับ stamp ด้านบน"
date +%s.%N

echo
echo "================ เสร็จ — ส่ง diag_out.txt ให้ Claude ================"

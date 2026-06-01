# microROS-X — หุ่นกู้ภัยอัตโนมัติ RRR26

หุ่น Yahboom 4 ล้ออัตโนมัติสำหรับการแข่ง **RRR26 RoboRescue** (30-31 พ.ค. 2569 เซียร์รังสิต)

> 🏆 **ผลการแข่ง:** ผ่านทุกรอบ — vision อ่าน AprilTag แม่น 100%, servo/nav ทำงานสะอาด ไม่มี FAILED loop

## Stack

ROS 2 Humble + Nav2 + slam_toolbox + AprilTag (tag36h11) + servo dispenser

หุ่น **ไม่ได้** รัน ROS 2 เอง — สื่อสารด้วย micro-ROS (DDS-XRCE) ผ่าน Wi-Fi UDP ไปยัง Docker agent บนเครื่อง host ที่ทำหน้าที่ bridge เข้าสู่ ROS 2 graph

> โค้ด คอมเมนต์ และ commit ทั้งหมดเป็น**ภาษาไทย** — ทำตามสไตล์เดิม

## โครงสร้าง 3 เฟส (3 โฟลเดอร์)

แต่ละเฟสรันจากในโฟลเดอร์ตัวเอง (ต้อง `cd` เข้าไปก่อน เพราะ launch file อิง CWD):

| เฟส | โฟลเดอร์ | หน้าที่ |
|---|---|---|
| 1. Bring-up | `start_up_robot/` | ตั้งค่าหุ่นผ่าน USB-serial, start micro-ROS agents, teleop, watchdog |
| 2. SLAM | `slam_map/` | slam_toolbox online_async + ขับสร้างแผนที่ → save `my_robot_map.{pgm,yaml}` |
| 3. Navigation | `navigator_map/` | Nav2 + waypoint mission + vision + servo drop (สแต็กวันแข่ง) |

**การส่งแผนที่ทำมือ:** copy `my_robot_map.pgm` + `my_robot_map.yaml` จาก `slam_map/` ไป `navigator_map/` หลัง mapping ทุกครั้ง

## เริ่มใช้งานเร็ว

```bash
# เฟส 1 — bring-up
cd start_up_robot
./start_agent_computer.sh           # micro-ROS agent หุ่น (port 8090)
./start_Camera_computer.sh          # micro-ROS agent กล้อง ESP32 (port 9999)
python3 config_robot_<wifi>.py      # ตั้ง SSID/agent IP/PID/domain id (ครั้งเดียว ผ่าน USB)

# เฟส 2 — SLAM
cd ../slam_map
./slam_map.sh                       # slam_toolbox + RViz
./save_map.sh                       # เซฟแผนที่
cp my_robot_map.* ../navigator_map/

# เฟส 3 — navigation / mission
cd ../navigator_map
./run_all_mission.sh                # nav2_launch + Cam_Pose_AprilTag + navigator_script
```

## เอกสาร

- **`CLAUDE.md`** — คู่มือสำหรับ Claude Code + gotchas สำคัญ (อ่านก่อนแก้โค้ด)
- **`navigator_map/CLAUDE.md`** — สถาปัตยกรรมสแตก Nav2 วันแข่ง (source of truth)
- **`navigator_map/docs/KNOWLEDGE.md`** — tutorial เจาะลึกทั้ง pipeline
- **`navigator_map/docs/RACE_LESSONS_RRR26.md`** — บทเรียนวันแข่งจริง
- **`navigator_map/docs/RRR26.pdf`** — กติกาทางการ
- **`คู่มือวันแข่ง_RRR26.md`** / **`yahboom_microros_robot_manual.md`** — คู่มือปฏิบัติงาน

## config ต่อ WiFi

`start_up_robot/` มี `config_robot_*.py` หนึ่งไฟล์ต่อ WiFi ที่ flash ไว้แล้ว — วันแข่งเลือกตัวที่ตรงกับ WiFi 2.4 GHz ของสนาม หรือ copy + แก้ SSID/password/agent IP ตัวใหม่ (Domain ID ต้องตรงกันระหว่าง config หุ่นกับ `ROS_DOMAIN_ID` ของ host, default 99)

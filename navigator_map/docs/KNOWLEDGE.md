# สรุปความรู้: RoboRescue with microROS

โน้ตสรุปเนื้อหาทั้งหมดของโปรเจกต์ Tutorial-RoboRescue-with-microROS สำหรับใช้อ้างอิงเร็ว ๆ

---

## 1. ภาพรวมระบบ

หุ่นยนต์กู้ภัย (Yahboom 4-wheel differential drive) สำหรับการแข่ง RoboRescue บนสนาม 320×280 cm
ใช้ **micro-ROS** บน ESP32 คุยกับ **ROS 2 Humble** บนคอมพิวเตอร์ฝั่ง host ผ่าน Wi-Fi

```
┌──────────────────┐        Wi-Fi UDP4         ┌──────────────────────┐
│  ESP32 (Robot)   │  ◄────── port 8090 ─────► │  Host PC (Ubuntu)    │
│  - micro-ROS     │                            │  - micro-ROS Agent   │
│  - มอเตอร์/IMU   │                            │    (Docker)          │
│  - LiDAR/Servo   │                            │  - ROS 2 Humble      │
└──────────────────┘                            │  - Nav2 / SLAM       │
                                                 │  - RViz2             │
┌──────────────────┐        Wi-Fi UDP4         │                      │
│  ESP32 Camera    │  ◄────── port 9999 ─────► │                      │
└──────────────────┘                            └──────────────────────┘
```

**สำคัญ:** หุ่นยนต์ **ไม่ได้** รัน ROS 2 เอง — มันคุย micro-ROS (DDS-XRCE) มา Agent บน host แล้ว Agent ค่อย bridge เข้า ROS 2 graph

---

## 2. Hardware Stack

| ส่วนประกอบ | รายละเอียด |
|---|---|
| ฐานหุ่น | Yahboom 4-wheel differential drive |
| MCU | ESP32 (รันเฟิร์มแวร์ micro-ROS) |
| LiDAR | RPLiDAR (publish `/scan`) |
| กล้อง | ESP32 Camera Module (แยก agent) |
| Servo | ใช้ปล่อยของ (payload drop) ผ่าน `/servo_s1` |
| Sensor อื่น ๆ | IMU, Battery monitor, Buzzer |
| USB | CP210x (มี driver ใน `Driver/` สำหรับ Windows) |

---

## 3. Software Stack

- **OS:** Ubuntu + ROS 2 Humble
- **Container:** Docker → `microros/micro-ros-agent:humble`
- **SLAM:** `slam_toolbox` (online_async mode)
- **Navigation:** `Nav2` (RPP controller default, มี DWB ให้เลือก)
- **Vision:** OpenCV + `pupil-apriltags` (tag36h11) — *MediaPipe Pose ถอดออกแล้ว*
- **Bringup package:** `yahboomcar_bringup`, `yahboom_esp32_camera`
- **Custom msgs:** `yahboomcar_msgs` (มี `PointArray`)
- **Teleop:** keyboard + LiDAR safety stop (~30 cm)

---

## 4. ROS Topics หลัก

| Topic | Type | ทิศทาง | หมายเหตุ |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | host → robot | ความเร็วเชิงเส้น/เชิงมุม |
| `/scan` | `sensor_msgs/LaserScan` | robot → host | LiDAR |
| `/imu` | `sensor_msgs/Imu` | robot → host | IMU |
| `/battery` | `std_msgs/UInt16` | robot → host | ค่า = โวลต์ × 10 |
| `/servo_s1` | `std_msgs/Int32` | host → robot | **-90 = เตะลง, 0 = คืนตำแหน่ง** (pulse, ไม่ latch — ต้อง publish ซ้ำ) |
| `/vision/detect_enable` | `std_msgs/Bool` | host → host | gate เปิด/ปิด vision pipeline (ปิดไว้ระหว่างวิ่งประหยัด CPU) |
| `/beep` | `std_msgs/UInt16` | host → robot | เสียง buzzer |
| `/espRos/esp32camera` | image | camera → host | ภาพจาก ESP32 cam |
| `/vision/latest_at_id` | `std_msgs/String` | host → host | ID AprilTag ล่าสุด |

> `/mediapipe/points` (landmark มนุษย์) **ถูกถอดออกแล้ว** — ไม่มี MediaPipe ในระบบรันจริง; person waypoint รู้จาก `type` ใน YAML

---

## 5. การตั้งค่าหุ่นยนต์ (Robot Config)

ตั้งค่าผ่าน **USB Serial** ก่อนใช้งานครั้งแรก (สคริปต์ `start_up_robot/config_robot_RRR26.py`)

- **Port:** `/dev/ttyUSB0`
- **Baudrate:** 115200
- **โปรโตคอล:** binary, head `0xFF`, device id `0xF8`, return id `0xF7`

ค่าที่ตั้งได้ (อ้างอิงจากตาราง `ORDER` ในโค้ด):

| คำสั่ง | Address |
|---|---|
| WIFI_SSID | 0x01 |
| WIFI_PASSWD | 0x02 |
| AGENT_IP | 0x03 |
| AGENT_PORT | 0x04 |
| CAR_TYPE | 0x05 |
| DOMAIN_ID | 0x06 |
| SERIAL_BAUDRATE | 0x07 |
| SERVO_OFFSET | 0x08 |
| MOTOR_PID | 0x09 |
| IMU_YAW_PID | 0x0A |
| ROS_NAMESPACE | 0x0B |
| REBOOT_DEVICE | 0x20 |
| RESET_CONFIG | 0x21 |
| REQUEST_DATA | 0x50 |
| FIRMWARE_VERSION | 0x51 |

**ค่าตัวอย่างที่ใช้ในห้องเรียน:**
- Wi-Fi: `wifi-inex` / `123456789-0`
- Agent IP/Port: `<REDACTED-IP>:8090`
- Domain ID: 99
- ROS Serial Baudrate: 921600
- Motor PID: 1, 0.2, 0.2
- IMU YAW PID: 1, 0, 0.2

**ในโปรเจกต์นี้:** มี template เดียว `start_up_robot/config_robot_RRR26.py` —
แก้ placeholder SSID/password/agent-IP ให้ตรง WiFi ที่ใช้ก่อนรันทุกครั้ง (กติกาแข่งต้อง 2.4 GHz ของผู้จัด)

---

## 6. micro-ROS Agent (Docker)

รัน Agent 2 ตัวพร้อมกัน คนละพอร์ต:

```bash
# Robot base (port 8090)
docker run -it --rm --name uros_agent_8090 \
  -v /dev:/dev -v /dev/shm:/dev/shm \
  --privileged --net=host \
  microros/micro-ros-agent:humble udp4 --port 8090 -v4

# ESP32 Camera (port 9999)
docker run -it --rm --name uros_agent_9999 \
  -v /dev:/dev -v /dev/shm:/dev/shm \
  --privileged --net=host \
  microros/micro-ros-agent:humble udp4 --port 9999 -v4
```

มีสคริปต์ wrapper ให้แล้ว: `start_agent_computer.sh` และ `start_Camera_computer.sh`

---

## 7. Workflow 3 เฟส

### เฟส 1: Bring-up (`microROS-X_Example/start_up_robot/`)

```bash
./start_agent_computer.sh     # เปิด agent หุ่นยนต์
./start_Camera_computer.sh    # เปิด agent กล้อง
./check_robot.sh              # เปิด 3 หน้าต่าง: cam viewer + teleop + vision
```

ไฟล์สำคัญ:
- `config_robot_RRR26.py` — class `MicroROS_Robot` ตั้งค่าผ่าน serial
- `ctrl_robot.py` — keyboard teleop + LiDAR safety stop (30 cm) + servo control (`p`)
- `Cam_Pose_AprilTag.py` — MediaPipe pose + AprilTag detection + dashboard
- `watchdog.py` — แสดงสถานะ camera/IMU/battery real-time
- `SET_Camera.py`, `config_camera.py` — ตั้งค่ากล้อง ESP32

### เฟส 2: SLAM Mapping (`microROS-X_Example/slam_map/`)

```bash
./slam_map.sh         # launch slam_toolbox + RViz
# ขับหุ่นด้วย ctrl_robot.py จากเฟส 1
./save_map.sh         # บันทึก my_robot_map.pgm + .yaml
```

พารามิเตอร์ SLAM ที่ใช้ (`map_slamtoolbox_launch.py`):
- `resolution`: 0.05 (5 cm/pixel)
- `max_laser_range`: 3.0 m
- `minimum_travel_distance`: 0.15 m
- `minimum_travel_heading`: 0.05 rad (~2.8°)
- `do_loop_closing`: true
- TF offset: `base_link → laser_frame` = (-0.0046412, 0, 0.094079)

### เฟส 3: Navigation (`microROS-X_Example/navigator_map/`)

```bash
ros2 launch nav2_launch.py                       # default เปิด RViz
ros2 launch nav2_launch.py open_rviz:=false      # ไม่เปิด RViz
python3 navigator_script.py                       # วิ่งตาม waypoints
```

ไฟล์สำคัญ:
- `nav2_launch.py` — รวม yahboomcar_bringup + nav2_bringup (**โหลด `prarams/dwb_nav_params.yaml`**)
- `navigator_script.py` — loop อ่าน waypoints + clearAllCostmaps ก่อนทุก goToPose + watchdog
  (no-progress >10s หรือ hard timeout 120s → cancel + retry) + เรียก mission_script
- `mission_script.py` — รับ argv `person|tag`:
  - `person` → **ไม่ใช้กล้อง** ปล่อย servo ทันที (YAML ระบุว่ามีคน) — 2 strikes/จุด
  - `tag` → subscribe `/vision/latest_at_id` เก็บโหวต warmup 2.5s → ตัดสิน ID เสียงข้างมาก
  - ไม่เจอใน warmup → หมุน 0.15 rad/s หาต่อ (เพดานทั้ง mission 11s)
- `Cam_Pose_AprilTag.py` — vision node, gated ด้วย `/vision/detect_enable` (ปิดประหยัด CPU ระหว่าง nav)
- `nav_waypoints.yaml` — รายการ waypoints + optional `via:` list สำหรับจุดคั่นบังคับเส้นทาง
- `get_waypoint.py` / `ctrl_robot_get_waypoint.py` — capture pose; ตัวหลังเช็ค AMCL covariance ก่อน save
- `cal_yaw.py` — แปลง yaw เป็น quaternion z/w

รูปแบบ `nav_waypoints.yaml`:
```yaml
waypoints:
- task: waypoint_1
  type: person          # person = drop servo เมื่อเจอคน | tag = อ่าน AprilTag
  x: 0.715
  y: -0.408
  orientation: {z: -0.75902, w: 0.65107}
- task: waypoint_3
  type: tag
  x: 2.476
  y: -1.299
  orientation: {z: 0.99994, w: -0.01135}
  via:                  # optional — จุดคั่นบังคับเส้นทาง (ไม่รัน mission)
    - x: 2.65
      y: 0.05
      orientation: {z: -0.7071, w: 0.7071}
- task: HOME            # ชื่อ HOME (ตัวพิมพ์ใหญ่ตัด case-insensitive) = ไม่รัน mission
  x: 0.0
  y: 0.0
  orientation: {z: 0.0, w: 1.0}
```

Controller:
- **`prarams/dwb_nav_params.yaml` คือไฟล์ที่โหลดจริง** (DWB Local Planner)
- `prarams/rpp_nav_params.yaml` อยู่ในโฟลเดอร์ แต่ไม่มีอะไรโหลด — แก้ไม่มีผล

---

## 8. Vision Pipeline

```
ESP32 Camera ─► /espRos/esp32camera ─► Cam_Pose_AprilTag.py
                                            │  (gate: /vision/detect_enable Bool, default OFF)
                                            └─► pupil-apriltags (tag36h11)
                                                  └─► /vision/latest_at_id (String)
```

ใช้ AprilTag tag36h11 ติดในสนามเพื่อระบุ ID จุดสำคัญ. โหนด vision รัน **เฉพาะ AprilTag** และ default ปิด (`/vision/detect_enable=False`) เพื่อประหยัด CPU — `navigator_script` เปิดเฉพาะตอนถึง tag waypoint แล้วปิดใน `finally`.

> **MediaPipe Pose ถูกถอดออกแล้ว** — `/mediapipe/points` ไม่มีอีกต่อไป. person waypoint รู้จาก field `type` ใน YAML ตรง ๆ ไม่ใช้กล้อง/ตรวจจับ (กฎให้คะแนน "กล่องลงกรอบแดง" ไม่ใช่ "ตรวจเจอคนก่อน").

---

## 9. Mission Logic (ค่าเริ่มต้น)

`navigator_script.py` + `mission_script.py` ทำงานร่วมกันแบบนี้:

1. อ่าน `nav_waypoints.yaml`
2. รับ input ลำดับ waypoint จาก user (เช่น `1,2,3,4,5`)
3. วน waypoint ทีละจุด:
   - มี `via:` → goToPose จุดคั่นก่อน (ไม่รัน mission) แล้วค่อยไป waypoint หลัก
   - clearAllCostmaps ก่อนทุก goToPose + watchdog (no-progress 10s / hard timeout 120s)
4. เมื่อถึงจุด:
   - ถ้าชื่อ = `HOME` → แค่หยุด 2 วิ (ไม่รัน mission)
   - ถ้าอื่น ๆ → set `/vision/detect_enable=True` → `subprocess.run(["python3", "-u", "mission_script.py", wp_type])` (blocking) → finally: set False
     - **`person` mode**: **ไม่ใช้กล้อง/ตรวจจับ** — timer 0.05s เรียก `_person_drop_immediately` ปล่อย servo ทันที (YAML ระบุว่ามีคนอยู่แล้ว)
     - **`tag` mode**: subscribe `/vision/latest_at_id`, รอ DDS link ≤ `LINK_TIMEOUT_SEC`=3.0s → ยืนนิ่งสแกน `WARMUP_SEC`=2.5s เก็บโหวต, ถ้า ≥ `WARMUP_VOTE_MIN`=3 เฟรม → `Counter.most_common` ตัดสิน, ไม่งั้นหมุน `ROTATE_SPEED`=0.15 rad/s เก็บต่อจนได้ ≥ `SPIN_VOTE_MIN`=10 เฟรม
     - `MISSION_TIMEOUT_SEC`=11.0s เพดานทั้ง mission — timeout แล้วหยุดล้อ + emit เสียงข้างมากเท่าที่มี (หุ่นหมุนหา tag = "ยังขยับ" กรรมการ approve เกิน 10s ได้)
5. ไป waypoint ถัดไป — ถ้า FAILED/CANCELED ระหว่างทาง break ทั้งแผน
6. กลับ prompt loop ใหม่ (reload YAML ทุกครั้ง แก้ไฟล์ระหว่างรันได้)

**Servo drop (person):** รอ subscriber `/servo_s1` ≤ `SERVO_LINK_SEC`=3s แล้วสวิง **2 strikes** (ปล่อย 2 กล่อง/จุด เป็น margin): pre-load `+89` (0.7s) → `-89` (0.6s, strike 1) → `+89` (0.6s) → `-89` (0.6s, strike 2) → `0` (0.3s). แต่ละมุม publish ซ้ำทุก 0.1s ตลอด hold (กัน DDS discovery race / QoS drop กินคำสั่งแรกหาย).

**สำคัญ:** `mission_script` exit 0 เสมอ แม้ servo ไม่เตะ/หาตัวไม่เจอ — `navigator_script` ดูแค่ `TaskResult.SUCCEEDED` จาก Nav2 ไม่ได้รู้ผล mission

---

## 10. จุดที่ต้องระวัง (Gotchas)

1. **โฟลเดอร์ `prarams/`** — สะกดผิดในโค้ดจริง (`prarams` ไม่ใช่ `params`) อย่าเปลี่ยนชื่อข้างเดียว
2. **Relative path** — launch files ใช้ `os.path.abspath()` กับ CWD ต้องรันจากในโฟลเดอร์เฟสนั้น ๆ
3. **TF offset ซ้ำ 2 ที่** — `slam_map/map_slamtoolbox_launch.py` กับ `navigator_map/nav2_launch.py` มี static TF `base_link → laser_frame` เหมือนกัน แก้แล้วต้องแก้ทั้งคู่
4. **ไม่ใช่ ROS package** — ไม่มี `setup.py`/`package.xml` รันด้วย path ตรง ๆ
5. **Servo เป็น pulse** — `-90` เตะลงแล้วตามด้วย `0` คืนตำแหน่ง; ต้อง **publish ซ้ำทุก 0.1s** ตลอดช่วง hold (1.0s ต่อมุม) ไม่งั้น DDS discovery race จะกินคำสั่งแรกหาย
6. **ภาษาไทยใน comments/prints** — รักษาภาษาเดิมเวลาแก้
7. **Domain ID ต้องตรงกัน** — host PC ต้อง `export ROS_DOMAIN_ID=20` ให้ตรงกับที่ตั้งไว้ในหุ่น
8. **ต้อง copy map ข้ามเฟส** — `my_robot_map.yaml/.pgm` ที่ save จาก slam_map ต้องเอาไปวางใน navigator_map ก่อนรัน Nav2

---

## 11. คำสั่งที่ใช้บ่อย

```bash
# ตรวจว่าหุ่นเชื่อมต่อ ROS graph ได้แล้ว
ros2 topic list
ros2 topic echo /battery
ros2 topic echo /scan --once

# ขับด้วยมือ
cd microROS-X_Example/start_up_robot && python3 ctrl_robot.py

# ทำแผนที่
cd microROS-X_Example/slam_map && ./slam_map.sh
# ... ขับวน ...
./save_map.sh

# Nav
cd microROS-X_Example/navigator_map
ros2 launch nav2_launch.py
python3 navigator_script.py

# เพิ่ม waypoint ขณะใช้งาน
python3 get_waypoint.py        # capture pose ปัจจุบันลง YAML
```

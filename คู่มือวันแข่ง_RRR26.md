# คู่มือใช้งานหุ่น RRR26 (วันแข่ง)

> **หุ่น:** Yahboom 4 ล้อ micro-ROS
> **สนาม:** ไดมอนด์ฮอลล์ ชั้น 5 เซียร์รังสิต — 30-31 พ.ค. 2569
> **คู่มือนี้สำหรับ:** ทีมงานที่ต้อง bring-up หุ่น + วิ่ง mission วันแข่ง

---

## 🗺️ ภาพรวม — ทำอะไรเมื่อไหร่

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│  Phase 1        │ →  │  Phase 2     │ →  │  Phase 3        │
│  bring-up หุ่น  │    │  ทำแผนที่    │    │  วิ่ง mission   │
│                 │    │  (SLAM)      │    │  (race day!)    │
│ start_up_robot/ │    │  slam_map/   │    │  navigator_map/ │
└─────────────────┘    └──────────────┘    └─────────────────┘
   ทุกครั้งที่เปิด        ทำครั้งเดียว         ทำทุกรอบแข่ง
   เครื่อง                ตอนซ้อม
```

**สำคัญ:** ทั้ง 3 phase อยู่คนละ folder ต้อง `cd` เข้าไปก่อนรันเสมอ

---

## ✅ Checklist สั้นๆ ก่อนแข่ง

- [ ] หุ่นเปิดได้ ไฟติด แบตเต็ม (>7.8V)
- [ ] PC ต่อ WiFi สนาม 2.4 GHz ได้
- [ ] รู้ IP ของ PC ตัวเอง (`hostname -I`)
- [ ] รู้ `ROS_DOMAIN_ID` ของ PC (`echo $ROS_DOMAIN_ID`)
- [ ] มีไฟล์แผนที่ `my_robot_map.pgm` + `.yaml` ใน `navigator_map/`
- [ ] เสากล้อง ESP32 ติดแน่น เลนส์สะอาด
- [ ] Servo ปืนกระสุน (กล่องชิงชีพ) โหลดไว้ 4-5 กล่อง
- [ ] LiDAR ไม่มีอะไรบัง

---

# 📕 Phase 1 — bring-up หุ่น

ทำทุกครั้งที่เปิดเครื่อง / ย้ายสนาม

## 1.1 ตั้งค่า WiFi + Agent IP (ครั้งแรกเท่านั้น)

> **ทำเมื่อไหร่:** เปลี่ยน WiFi / เปลี่ยนเครื่อง / เปลี่ยน `ROS_DOMAIN_ID`
> **ทำที่ไหน:** USB-serial เสียบหุ่นกับ PC

### ขั้นตอน
1. เสียบสาย USB จากหุ่นเข้า PC
2. เช็คว่าหุ่นโผล่เป็น `/dev/ttyUSB0`:
   ```bash
   ls /dev/ttyUSB*
   ```
   > ⚠️ **ถ้าไม่เจอ** = brltty แย่งพอร์ต! แก้:
   > ```bash
   > sudo apt-get purge brltty
   > sudo rm -f /usr/lib/udev/rules.d/85-brltty.rules
   > sudo pkill brltty
   > ```
   > แล้วถอด-เสียบสายใหม่

3. หา IP ของ PC ตัวเอง:
   ```bash
   hostname -I
   # เช่นได้ → <REDACTED-IP>
   ```

4. แก้ไฟล์ `start_up_robot/config_robot_RRR26.py` บรรทัด 515-520:
   ```python
   robot.set_wifi_config("ชื่อ_WiFi_สนาม", "รหัสผ่าน")     # ← แก้
   robot.set_udp_config([0,0,0,0], 8090)         # ← IP ของ PC
   robot.set_ros_domain_id(99)                              # ← ตรงกับ PC
   ```
   > ⚠️ **DOMAIN_ID ต้องตรงกับ PC** ไม่งั้นคุยกันไม่รู้เรื่อง
   > เช็ค PC: `echo $ROS_DOMAIN_ID`

5. รัน:
   ```bash
   cd start_up_robot
   python3 config_robot_RRR26.py
   ```

6. **ปิด-เปิดสวิตช์หุ่น** ให้ค่าใหม่มีผล

> 💡 ใช้ WiFi อื่น/วงอื่น: แก้ placeholder SSID/password/agent-IP ใน `config_robot_RRR26.py` ให้ตรงวงนั้น (หรือ copy ไฟล์ไปตั้งชื่อใหม่)

---

## 1.2 เปิด micro-ROS Agent (ทุกครั้งที่ run)

หุ่นไม่ได้พูด ROS 2 ตรงๆ ต้องมี "ล่าม" (agent) ทำงานบน PC

### เปิด 2 terminal:

**Terminal A** — agent หุ่น (มอเตอร์/IMU/LiDAR/servo):
```bash
cd start_up_robot
./start_agent_computer.sh
```
> รอจนเห็นข้อความเหมือน `session established` ก็แปลว่าหุ่นเชื่อมแล้ว

**Terminal B** — agent กล้อง ESP32:
```bash
cd start_up_robot
./start_Camera_computer.sh
```

> 💡 ทั้ง 2 ตัวรันเป็น **docker container** ถ้าค้างให้กด Ctrl+C แล้วรันใหม่ — script จะลบ container เก่าให้เอง

---

## 1.3 เช็คว่าหุ่นพร้อม (watchdog)

**Terminal C:**
```bash
cd start_up_robot
python3 watchdog.py
```

จะเห็นแบบนี้:
```
[12:34:56] Cam: ONLINE  | IMU: ONLINE (IMU.Z: 9.78)
           BAT: 7.92 V  | LiDAR: ONLINE | Odom: ONLINE
```

✅ **ครบ 5 ตัว ONLINE + BAT > 7.8V** = พร้อมไปต่อ Phase 3

❌ **ถ้ามีตัวไหน OFFLINE:**
| ตัวที่ offline | สาเหตุ/แก้ |
|---|---|
| Cam | เช็ค `./start_Camera_computer.sh` ทำงานอยู่ไหม / WiFi ESP32 ติด |
| IMU | ปิด-เปิดสวิตช์หุ่น |
| BAT | เปลี่ยนแบต (< 7.2V อันตราย) |
| LiDAR | สาย LiDAR หลวมหรือยัง / ตัวหุ่นเปิดไหม |
| Odom | agent หุ่น (T-A) ไม่ทำงาน |

---

# 📗 Phase 2 — ทำแผนที่ (ครั้งเดียวตอนซ้อม)

ทำตอน rehearsal/practice (วันก่อนแข่ง) **ไม่ได้ทำซ้ำหน้างาน** เพราะแผนที่ดีอันเดียวพอ

### ขั้นตอน

1. ทำ Phase 1 ให้เสร็จก่อน (agent + watchdog ครบ)

2. **Terminal A** — เปิด SLAM:
   ```bash
   cd slam_map
   ./slam_map.sh
   ```
   จะเปิด RViz ขึ้นมา เห็น LiDAR scan

3. **Terminal B** — ขับหุ่นไปสำรวจ:
   ```bash
   cd slam_map
   python3 ctrl_robot.py
   ```
   ใช้ปุ่ม WASD ขับช้าๆ ให้ทั่วสนาม โดยเฉพาะ:
   - มุมห้อง
   - pocket ของผู้ประสบภัย
   - บริเวณ HOME

4. ดู RViz จนแผนที่ครอบคลุมหมด **แล้วยังไม่ปิด**

5. **Terminal C** — บันทึก:
   ```bash
   cd slam_map
   ./save_map.sh
   ```
   จะได้ไฟล์ `my_robot_map.pgm` + `my_robot_map.yaml` ใน `slam_map/`

6. **คัดลอกไป Phase 3:** (สำคัญมาก!)
   ```bash
   cp slam_map/my_robot_map.* navigator_map/
   ```

> ⚠️ **อย่าลืม copy!** ถ้าลืม Phase 3 จะใช้แผนที่เก่า

---

# 📘 Phase 3 — วันแข่งจริง

นี่คือส่วนที่ใช้ทุกรอบ

## 3.1 เตรียมก่อน launch

1. ทำ Phase 1 ครบ (agent + watchdog GREEN)
2. แผนที่ใหม่ copy เข้า `navigator_map/` แล้ว
3. **อ่าน briefing จากกรรมการ** — ตำแหน่งผู้ประสบภัย + AprilTag ID **เปลี่ยนทุกรอบ**

## 3.2 แก้ waypoints ตามตำแหน่งจริง

เปิดไฟล์:
```bash
nano navigator_map/nav_waypoints.yaml
```

แก้ตำแหน่ง + ประเภท (`person` หรือ `tag`) ให้ตรงกับที่กรรมการบอก

> 💡 อยากบันทึก waypoint ใหม่จาก position จริง? ขับหุ่นไปจุดนั้นแล้วรัน:
> ```bash
> cd navigator_map
> python3 get_waypoint.py
> # กด 's' เพื่อ save
> ```

## 3.3 วางหุ่นที่จุดสตาร์ท

> 🛑 **กฎเหล็ก:** วางหุ่นที่ **(0, 0) หัน +x (ทิศไปข้างหน้า) เป๊ะๆ** ก่อนกด launch
>
> ถ้าวางผิด → AMCL หาตำแหน่งจาก LiDAR ผิดที่ → costmap ทับตัวหุ่น → waypoint แรก fail ทันที

## 3.4 Launch!

```bash
cd navigator_map
./run_all_mission.sh
```

จะเปิด 3 หน้าต่าง terminator:
| หน้าต่าง | ทำอะไร |
|---|---|
| **nav2_launch** | Nav2 + AMCL + RViz |
| **Cam_Pose_AprilTag** | กล้อง + ตรวจคน + ตรวจ tag |
| **navigator_script** | ตัวสั่ง mission (interactive) |

รอจนเห็น `Nav2 active` แล้ว navigator จะถามว่า:
```
ลำดับ waypoint?
```

พิมพ์ลำดับที่จะวิ่ง เช่น `1,2,3,4,5` กด Enter
> รัน mission เสร็จ พิมพ์ `0` เพื่อจบ

## 3.5 ระหว่างวิ่ง — สังเกตอะไร?

หุ่นจะทำแบบนี้ที่แต่ละ waypoint:
```
1. ขับไปถึง waypoint (clearCostmap + Nav2)
2. หยุดนิ่ง 2.5 วินาที (warmup ตรวจหา)
3. ถ้าไม่เจอ → หมุนช้าๆ หา
4. เจอคน → ยิง servo ปล่อยกล่อง (-90° ค้าง 1s → 0° ค้าง 1s)
   เจอ tag → log ID ไว้
5. ไป waypoint ถัดไป
```

## 3.6 ถ้าผิดพลาด — แก้ยังไง

### หุ่นค้าง > 10 วิ (กรรมการจะบังคับ retry)
- กด Ctrl+C ที่ navigator window → `emergency_stop()` จะหยุดล้อให้
- รอกรรมการรีเซ็ตหุ่น แล้ว launch ใหม่

### หุ่นชนกำแพง / หลงทาง
1. กด Ctrl+C ที่ navigator
2. **อย่า `pkill -9`!** ล้อจะหมุนค้าง — เพราะคำสั่งสุดท้ายค้างใน firmware
3. ถ้าจำเป็นต้อง kill จริงๆ ส่ง zero velocity ก่อน:
   ```bash
   ros2 topic pub /cmd_vel geometry_msgs/Twist '{}' -1
   # ทำซ้ำ 5 ครั้ง
   ```

### Extrapolation Error / TF error
```bash
cd navigator_map
bash diag.sh 2>&1 | tee diag_out.txt
```
ดูว่า `/scan` `/odom` `/tf` rate ปกติไหม

### ระหว่างรอบ — เปลี่ยน waypoint
1. กด `0` ออกจาก navigator (Nav2 + vision ยังรันได้)
2. แก้ `nav_waypoints.yaml`
3. รันใหม่: `python3 navigator_script.py`

### ยกหุ่นออก-วางใหม่
- ต้อง **launch ทั้งหมดใหม่** (Ctrl+C ทุก window + รัน `run_all_mission.sh` ใหม่)
- เพราะ AMCL seed pose หลุดถาวร

---

# 🚨 กฎเหล็ก 6 ข้อ — ห้ามลืม

1. **ก่อน `pkill` หรือ Ctrl+C → ปล่อย zero `/cmd_vel` ก่อน** ไม่งั้นล้อหมุนค้าง
2. **วางหุ่น (0,0) หัน +x เป๊ะ** ก่อน launch Phase 3
3. **`prarams/` สะกดผิดตั้งใจ** (ไม่ใช่ `params/`) อย่าแก้!
4. **อย่าเปลี่ยน footprint เป็น `robot_radius`** หุ่นจะเข้า pocket แคบไม่ได้
5. **DOMAIN_ID หุ่น = DOMAIN_ID PC** ไม่งั้นไม่คุยกัน
6. **copy แผนที่จาก `slam_map/` ไป `navigator_map/` หลังทำ SLAM เสร็จ**

---

# 📞 ติดต่อทีม / debug

- log ของแต่ละ phase อยู่ที่ `/tmp/nav2.log`, `/tmp/vision.log`, `/tmp/navigator.log`
- กติกาเต็ม + ภาพสนาม/zone ผู้ประสบภัย: `navigator_map/docs/RRR26.pdf`
- คู่มือ Yahboom hardware: `yahboom_microros_robot_manual.md`

---

**โชคดีวันแข่งครับ! 🤖🏆**

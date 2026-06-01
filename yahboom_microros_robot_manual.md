# คู่มือการใช้งานหุ่นยนต์ Yahboom MicroROS Robot Car (ESP32 + Virtual Machine)

> **สำหรับ:** สมาชิกทีมและน้องในทีม
> **เวอร์ชัน:** 1.0
> **อ้างอิง:** Yahboom Technology — ESP32 MicroROS Robot Car (Virtual Machine as controller)
> **แหล่งทางการ:**
> - GitHub: https://github.com/YahboomTechnology/Mirco-Ros-Car_VM
> - เอกสารทางการ: https://www.yahboom.net/study/MicroROS-ESP32
> - หน้าผลิตภัณฑ์: https://category.yahboom.net/products/microros-esp32

---

## สารบัญ

1. [บทนำ](#1-บทนำ)
2. [ภาพรวมของระบบ](#2-ภาพรวมของระบบ)
3. [รายละเอียดฮาร์ดแวร์](#3-รายละเอียดฮาร์ดแวร์)
4. [รายละเอียดซอฟต์แวร์](#4-รายละเอียดซอฟต์แวร์)
5. [โครงสร้างหลักสูตรของ Yahboom](#5-โครงสร้างหลักสูตรของ-yahboom)
6. [การเตรียมความพร้อมก่อนใช้งาน](#6-การเตรียมความพร้อมก่อนใช้งาน)
7. [การติดตั้งระบบ](#7-การติดตั้งระบบ)
8. [การใช้งานเบื้องต้น](#8-การใช้งานเบื้องต้น)
9. [การใช้งาน Lidar และการนำทาง](#9-การใช้งาน-lidar-และการนำทาง)
10. [การใช้งานขั้นสูง](#10-การใช้งานขั้นสูง)
11. [การบำรุงรักษา](#11-การบำรุงรักษา)
12. [การแก้ไขปัญหาเบื้องต้น](#12-การแก้ไขปัญหาเบื้องต้น)
13. [ความปลอดภัย](#13-ความปลอดภัย)
14. [ภาคผนวก](#14-ภาคผนวก)

---

## 1. บทนำ

### 1.1 เกี่ยวกับคู่มือนี้

คู่มือนี้จัดทำขึ้นเพื่อให้สมาชิกในทีมสามารถใช้งาน บำรุงรักษา และพัฒนาต่อยอดหุ่นยนต์ Yahboom MicroROS Robot Car ได้อย่างถูกต้องและปลอดภัย โดยอ้างอิงจากเอกสารและซอร์สโค้ดทางการของ Yahboom Technology

### 1.2 จุดเด่นของหุ่นยนต์รุ่นนี้

จากเอกสารทางการของ Yahboom สรุปได้ดังนี้

- ใช้ Virtual Machine บน PC เป็นตัวควบคุมหลักแทน Jetson NANO หรือ Raspberry Pi เพื่อลดต้นทุน
- บอร์ดควบคุม MicroROS มี ESP32 ในตัว ใช้ฟังก์ชัน WiFi UDP ของ MicroROS สำหรับสื่อสารระหว่างรถกับ Virtual Machine
- ใช้ ROS2-Humble และ Python3 พร้อมหลักสูตรและซอร์สโค้ดจำนวนมาก
- รองรับ Lidar Obstacle Avoidance, Following, Mapping Navigation, RVIZ Simulation, Multi-machine Synchronization Control และการควบคุมผ่าน APP/Handle
- โครงสร้างอลูมิเนียมอัลลอย พร้อมมอเตอร์ Encoder 310 และแบตเตอรี่ความจุสูง 7.4V

### 1.3 ความรู้พื้นฐานที่ควรมี

- ความเข้าใจพื้นฐานเรื่องระบบปฏิบัติการ Linux (คำสั่ง Terminal เบื้องต้น)
- ความรู้พื้นฐานภาษา Python3
- ความเข้าใจเรื่อง ROS2 (Node, Topic, Publisher, Subscriber)
- ความเข้าใจเรื่อง Docker เบื้องต้น

---

## 2. ภาพรวมของระบบ

### 2.1 สถาปัตยกรรมระบบ

หุ่นยนต์ตัวนี้ใช้สถาปัตยกรรมแบบ **กระจายการประมวลผล (Distributed Computing)** ผ่าน WiFi UDP

```
+------------------+        WiFi (UDP)         +-------------------+
|   PC + VMware    | <----------------------> |   ESP32 บนบอร์ด  |
|   (Ubuntu 22.04  |     micro-ROS Protocol    |   MicroROS        |
|    + ROS2 Humble)|                           |                   |
+------------------+                           +-------------------+
        |                                              |
        | คำนวณหนัก:                                  | ควบคุมระดับต่ำ:
        | - SLAM Mapping                               | - มอเตอร์ Encoder
        | - Navigation2                                | - IMU
        | - OpenCV + MediaPipe                         | - Lidar I/O
        | - การตัดสินใจ                                | - PWM Servo
        +----------------------------------------------+
```

### 2.2 หลักการทำงานโดยสรุป

1. เซ็นเซอร์ทั้งหมด (IMU, Lidar, Encoder) ส่งข้อมูลให้ ESP32
2. ESP32 แพ็คข้อมูลเป็นข้อความ ROS2 ส่งผ่าน WiFi UDP ไปยัง Virtual Machine
3. Virtual Machine ประมวลผลด้วย ROS2-Humble และ Python3
4. คำสั่งควบคุมส่งกลับมาที่ ESP32 เพื่อขับเคลื่อนมอเตอร์และเซอร์โว

### 2.3 ความสามารถหลัก

- การควบคุมระยะไกล (คีย์บอร์ด, จอย, แอปมือถือ)
- Lidar Obstacle Avoidance — หลบสิ่งกีดขวาง
- Lidar Following — ติดตามวัตถุ
- Lidar Guard — เฝ้าระวังพื้นที่
- Lidar Patrol — ลาดตระเวน
- Gmapping และ Cartographer Mapping — สร้างแผนที่
- Navigation2 — นำทางอัตโนมัติ
- Multi-machine Control — ควบคุมหลายตัวพร้อมกัน
- Robot Visual Interaction — ใช้ OpenCV และ MediaPipe

---

## 3. รายละเอียดฮาร์ดแวร์

### 3.1 บอร์ดควบคุมหลัก (MicroROS Control Board)

| รายการ | รายละเอียด |
|---|---|
| ชิปประมวลผล | ESP32 (Dual-core) |
| ช่องขับมอเตอร์ Encoder | 4 ช่อง |
| ช่องขับเซอร์โว PWM | 2 ช่อง |
| พอร์ตเชื่อมต่อ Lidar | 1 พอร์ต |
| เซ็นเซอร์ IMU | 6 แกนในตัว |

### 3.2 มอเตอร์

- **รุ่น:** 310 Encoder Motor
- **จำนวน:** 4 ตัว
- **คุณสมบัติ:** มี Encoder ในตัว สำหรับวัดความเร็วและคำนวณ Odometry

### 3.3 เซ็นเซอร์ IMU

- **ประเภท:** 6 แกน (Accelerometer 3 แกน + Gyroscope 3 แกน)
- **หน้าที่:** วัดการเอียง การหมุน และช่วยคำนวณ Odometry ร่วมกับ Encoder

### 3.4 Lidar

- **รุ่น:** ORBBEC MS200 (TOF Lidar)
- **คุณสมบัติ:** สแกน 360 องศา รองรับการ Mapping และ Navigation ทั้งในร่มและนอกอาคาร

### 3.5 แหล่งจ่ายไฟ

- **ประเภท:** แบตเตอรี่ลิเธียม
- **แรงดัน:** 7.4V
- **ความจุ:** 2000mAh
- **ระยะเวลาใช้งาน:** ประมาณ 5 ชั่วโมง

### 3.6 โครงสร้าง

- วัสดุอลูมิเนียมอัลลอย Anodized
- โครงสร้างปิดมิดซ่อนสายไฟ
- ทนทาน ทนการสึกหรอ

---

## 4. รายละเอียดซอฟต์แวร์

### 4.1 ระบบปฏิบัติการและเฟรมเวิร์ก

| รายการ | เวอร์ชัน/รายละเอียด |
|---|---|
| ระบบปฏิบัติการ | Ubuntu 22.04 LTS (ใน Virtual Machine) |
| ROS Distribution | ROS2 Humble Hawksbill |
| ภาษาโปรแกรม | Python3 |
| Communication | micro-ROS over WiFi UDP |
| Container | Docker (Image จาก Yahboom) |
| Computer Vision | OpenCV, MediaPipe |

### 4.2 เครื่องมือพัฒนา ESP32

- **ESP-IDF** — Framework ของ Espressif สำหรับพัฒนา ESP32
- **Flash Tool** — โปรแกรมแฟลชเฟิร์มแวร์
- **microROS Components** — ไลบรารีเชื่อมต่อ ROS2

### 4.3 Topic หลักของ ROS2

| Topic | ประเภท | หน้าที่ |
|---|---|---|
| `/cmd_vel` | `geometry_msgs/Twist` | รับคำสั่งความเร็ว |
| `/odom` | `nav_msgs/Odometry` | ส่งข้อมูล Odometry |
| `/scan` | `sensor_msgs/LaserScan` | ข้อมูลจาก Lidar |
| `/imu` | `sensor_msgs/Imu` | ข้อมูลจาก IMU |
| `/tf` | `tf2_msgs/TFMessage` | การแปลงพิกัด |
| `/joint_states` | `sensor_msgs/JointState` | สถานะของข้อต่อ/ล้อ |
| `/voltage` | `std_msgs/Float32` | แรงดันแบตเตอรี่ |
| `/map` | `nav_msgs/OccupancyGrid` | แผนที่ (ขณะ Mapping/Nav) |

> **หมายเหตุ:** Topic ที่แสดงข้างบนเป็นรายการทั่วไป ชื่อจริงของ Topic ในเวอร์ชันที่คุณใช้อาจแตกต่างกัน ให้ตรวจสอบด้วยคำสั่ง `ros2 topic list` หลังจากเชื่อมต่อหุ่นยนต์

---

## 5. โครงสร้างหลักสูตรของ Yahboom

หลักสูตรทางการของ Yahboom แบ่งออกเป็นบทเรียนดังนี้ (อ้างอิงจาก GitHub Repo ทางการ)

### 5.1 บทเรียนพื้นฐาน

| บท | หัวข้อ |
|---|---|
| 01 | Introduction (แนะนำผลิตภัณฑ์) |
| 02 | Assembly Course (การประกอบ) |
| 04 | VM Remote Control Course (การควบคุมระยะไกล) |
| 05 | ROS-WiFi Module Configuration |
| 12 | Linux Basic Course |
| 13 | Docker Course |

> **หมายเหตุ:** หลักสูตรของ Yahboom ข้ามบทที่ 03 ไป (ไม่มีในโครงสร้างไฟล์บน GitHub Repo) ซึ่งอาจเป็นบทที่ถูกรวมเข้ากับบทอื่นหรือยังไม่ได้เผยแพร่

### 5.2 บทเรียน ROS2 และ MicroROS

| บท | หัวข้อ |
|---|---|
| 14 | ROS2 Basic Course |
| 15 | microROS Control Board Development Environment |
| 16 | ESP32 Basic Course |
| 17 | microros Basic Course |

### 5.3 บทเรียนการใช้งานหุ่นยนต์

| บท | หัวข้อ |
|---|---|
| 06 | ROS+OpenCV Course |
| 07 | Mediapipe Course |
| 08 | Robot Basic Course |
| 09 | Lidar Course |
| 10 | Multi-machine Course |
| 11 | Robot Visual Interaction |

### 5.4 รายละเอียดบทที่ 08 (Robot Basic Course)

1. Robot Information Release
2. Robot Keyboard Control
3. Robot Handle Control
4. Robot State Estimation
5. Linear Speed Calibration
6. Angular Velocity Calibration
7. Robot URDF Model

### 5.5 รายละเอียดบทที่ 09 (Lidar Course)

1. Lidar Avoidance (หลบสิ่งกีดขวาง)
2. Lidar Following (ติดตาม)
3. Lidar Guard (เฝ้าระวัง)
4. Lidar Patrol (ลาดตระเวน)
5. Gmapping Mapping
6. Cartographer Mapping
7. Navigation2 Navigation Avoidance
8. ROS Robot APP Mapping
9. ROS Robot APP Navigation

### 5.6 รายละเอียดบทที่ 16 (ESP32 Basic Course)

1. Turn on the LED Light
2. Button Function
3. Drive the Buzzer
4. Serial Communication
5. Battery Voltage Detection
6. Drive PWM Servo
7. Drive Motor
8. Read Motor Encoder Data
9. PID Controls Car Speed
10. Read IMU Data
11. Read Radar Data
12. Flash Access Data
13. Partition Table and Memory
14. Bluetooth Communication
15. WiFi Networking
16. Robot Kinematics Analysis
17. ROS-WiFi Camera Module

---

## 6. การเตรียมความพร้อมก่อนใช้งาน

### 6.1 อุปกรณ์ที่ต้องเตรียม

- ตัวหุ่นยนต์ Yahboom MicroROS Robot Car
- คอมพิวเตอร์ที่ติดตั้ง VMware Workstation (แนะนำ) หรือ VirtualBox
- WiFi Router (แนะนำ 2.4 GHz)
- สาย USB Type-C (สำหรับแฟลชเฟิร์มแวร์)
- แบตเตอรี่ที่ชาร์จเต็ม (≥ 7.2V)
- คีย์บอร์ดหรือ Handle Controller

### 6.2 ดาวน์โหลด Virtual Machine Image

ลิงก์ทั้งหมดมีอยู่ในไฟล์ `All_Attachment_DownloadLinks.txt` จาก GitHub Repo ทางการ

> **หมายเหตุ:** ระบบปฏิบัติการ MacOS ไม่รองรับ Virtual Machine ของ Yahboom

### 6.3 ตรวจสอบก่อนเปิดเครื่อง

- [ ] แบตเตอรี่ติดตั้งถูกต้องและชาร์จไฟเพียงพอ (≥ 7.2V)
- [ ] สาย Lidar เชื่อมต่อแน่นหนา
- [ ] ล้อทั้ง 4 ขันแน่น ไม่หลวม
- [ ] สวิตช์อยู่ในตำแหน่ง OFF
- [ ] ไม่มีสายไฟพันที่ล้อหรือมอเตอร์

---

## 7. การติดตั้งระบบ

> **⚠️ หมายเหตุสำคัญ:** ชื่อ Workspace, Package, Container และคำสั่งบางส่วนในบทนี้และบทถัดไป อ้างอิงรูปแบบทั่วไปของ Yahboom กรุณายืนยันกับเอกสารหรือซอร์สโค้ดเวอร์ชันที่ติดมากับชุดของคุณก่อนใช้งานจริง โดยใช้คำสั่งต่อไปนี้ตรวจสอบ:
> ```bash
> ros2 pkg list | grep yahboom        # ดูชื่อ Package
> ls ~/                                # ดูชื่อ Workspace
> docker ps -a                         # ดูชื่อ Container
> ```

### 7.1 ติดตั้ง Virtual Machine

1. ดาวน์โหลด Image จาก Yahboom (รหัสผ่านมีในเอกสาร)
2. เปิด VMware Workstation
3. เลือก `File → Open` แล้วเลือกไฟล์ `.vmx`
4. กำหนดทรัพยากร: RAM อย่างน้อย 4 GB, CPU 2 cores ขึ้นไป
5. ตั้งค่า Network Adapter เป็น **Bridged Mode**

### 7.2 Login Virtual Machine

- **Username:** `yahboom`
- **Password:** `yahboom`

(ค่าเริ่มต้นจาก Yahboom — แนะนำให้เปลี่ยนรหัสผ่านหลังใช้งานครั้งแรก)

### 7.3 ตั้งค่า WiFi บนหุ่นยนต์ (ROS-WiFi Module)

1. เปิดสวิตช์หุ่นยนต์ รอจน LED แสดงสถานะพร้อม
2. ใช้โทรศัพท์เชื่อมต่อ WiFi Hotspot ของ ESP32
3. เปิดเบราว์เซอร์ไปที่ `<REDACTED-IP>`
4. กรอก SSID และ Password ของ WiFi ที่ต้องการให้หุ่นยนต์เชื่อมต่อ
5. กด Save แล้วรีสตาร์ตหุ่นยนต์
6. ตรวจสอบ IP ของหุ่นยนต์จาก Router

### 7.4 เข้า Docker Container

Yahboom เตรียม Docker Image ไว้แล้ว เพื่อความสะดวกในการพัฒนา

```bash
# เข้า Container
docker exec -it yahboom_ros bash

# หรือใช้สคริปต์ที่ Yahboom เตรียมไว้
~/docker_start.sh
```

### 7.5 ตรวจสอบการเชื่อมต่อ

```bash
# ตรวจ Ping
ping <robot_ip>

# Source ROS2
source /opt/ros/humble/setup.bash

# ดู Topic
ros2 topic list
```

ควรเห็น Topic เช่น `/cmd_vel`, `/odom`, `/scan`, `/imu`

---

## 8. การใช้งานเบื้องต้น

### 8.1 การเปิด-ปิดเครื่อง

**เปิดเครื่อง**
1. ตรวจสอบแบตเตอรี่
2. กดสวิตช์ ON
3. รอ LED สถานะแสดงว่าเชื่อมต่อ WiFi สำเร็จ

**ปิดเครื่อง**
1. หยุดทุก Node ก่อน (Ctrl+C)
2. กดสวิตช์ OFF
3. ห้ามถอดแบตขณะเครื่องยังทำงาน

### 8.2 Robot Keyboard Control (บทที่ 08.2)

ตามหลักสูตร Yahboom ใช้คำสั่ง

```bash
# Source ROS2 และ Workspace
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash

# รัน Keyboard Control
ros2 run yahboomcar_ctrl yahboom_keyboard
```

**ปุ่มควบคุม** (อาจแตกต่างกันเล็กน้อยตามเวอร์ชัน — ดูข้อความที่หน้าจอ)

| ปุ่ม | หน้าที่ |
|---|---|
| `i` | เดินหน้า |
| `,` | ถอยหลัง |
| `j` | หมุนซ้าย |
| `l` | หมุนขวา |
| `u` / `o` | เลี้ยวเดินหน้า ซ้าย/ขวา |
| `m` / `.` | เลี้ยวถอยหลัง ซ้าย/ขวา |
| `k` หรือ `Space` | หยุด |
| `q` / `z` | ปรับความเร็วสูงสุด |

### 8.3 ตรวจสอบข้อมูลเซ็นเซอร์

```bash
# ข้อมูล IMU
ros2 topic echo /imu

# ข้อมูล Lidar
ros2 topic echo /scan

# Odometry
ros2 topic echo /odom

# ดูความถี่
ros2 topic hz /scan
```

### 8.4 Robot State Estimation (บทที่ 08.4)

```bash
ros2 launch yahboomcar_bringup bringup.launch.py
```

จะเริ่ม Node สำคัญ เช่น micro-ROS Agent, robot_state_publisher และ TF

---

## 9. การใช้งาน Lidar และการนำทาง

> **หมายเหตุ:** ชื่อไฟล์ launch ในส่วนนี้อ้างอิงรูปแบบมาตรฐานของ Yahboom กรุณาตรวจสอบชื่อจริงในเอกสารหรือซอร์สโค้ดของเวอร์ชันที่คุณใช้

### 9.1 Lidar Avoidance (บทที่ 09.1)

```bash
ros2 launch yahboomcar_nav laser_Avoidance.launch.py
```

### 9.2 Lidar Following (บทที่ 09.2)

```bash
ros2 launch yahboomcar_nav laser_Tracker.launch.py
```

### 9.3 Lidar Guard (บทที่ 09.3)

```bash
ros2 launch yahboomcar_nav laser_Warning.launch.py
```

### 9.4 Lidar Patrol (บทที่ 09.4)

```bash
ros2 launch yahboomcar_nav laser_Patrol.launch.py
```

### 9.5 Gmapping Mapping (บทที่ 09.5)

**ขั้นตอนที่ 1: เริ่ม SLAM**

```bash
ros2 launch yahboomcar_nav map_gmapping.launch.py
```

**ขั้นตอนที่ 2: เปิด RVIZ**

```bash
ros2 launch yahboomcar_nav view_mapping.launch.py
```

**ขั้นตอนที่ 3: ขับสำรวจ**

เปิด Terminal อีกหน้าหนึ่งและรัน Keyboard Control ขับช้า ๆ ให้ Lidar สแกนได้ครบ

**ขั้นตอนที่ 4: บันทึกแผนที่**

```bash
ros2 run nav2_map_server map_saver_cli -f ~/maps/my_map
```

### 9.6 Cartographer Mapping (บทที่ 09.6)

```bash
ros2 launch yahboomcar_nav map_cartographer.launch.py
```

### 9.7 Navigation2 (บทที่ 09.7)

```bash
ros2 launch yahboomcar_nav navigation_dwa.launch.py map:=~/maps/my_map.yaml
```

ใน RVIZ ใช้ `2D Goal Pose` คลิกตำแหน่งเป้าหมาย หุ่นยนต์จะวางแผนเส้นทางและเคลื่อนที่อัตโนมัติ

### 9.8 ROS Robot APP

Yahboom มีแอปมือถือสำหรับควบคุมหุ่นยนต์ รองรับ Mapping และ Navigation ผ่านแอปโดยตรง สามารถดาวน์โหลดได้จากเอกสารทางการ

---

## 10. การใช้งานขั้นสูง

### 10.1 การเขียน Node ของตัวเอง

**ตัวอย่าง: Node สั่งหุ่นยนต์เดินหน้า**

```python
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

class MoveForward(Node):
    def __init__(self):
        super().__init__('move_forward')
        self.publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.timer = self.create_timer(0.1, self.publish_cmd)

    def publish_cmd(self):
        msg = Twist()
        msg.linear.x = 0.2   # ความเร็วเชิงเส้น (m/s)
        msg.angular.z = 0.0  # ความเร็วการหมุน (rad/s)
        self.publisher.publish(msg)

def main():
    rclpy.init()
    node = MoveForward()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

### 10.2 การ Calibrate (บทที่ 08.5 และ 08.6)

**Linear Speed Calibration (ปรับความเร็วเชิงเส้น)**

1. สั่งให้หุ่นยนต์เดินหน้าตรงด้วยความเร็วคงที่ในระยะทางที่กำหนด (เช่น 1 เมตร)
2. วัดระยะทางจริงที่หุ่นยนต์เคลื่อนที่ได้ด้วยตลับเมตร
3. หากระยะจริงต่างจากค่าที่ตั้ง ให้ปรับค่า `wheel_radius` (รัศมีล้อ) ใน Parameter
4. ทำซ้ำจนกว่าระยะจริงจะใกล้เคียงค่าที่ตั้ง

**Angular Velocity Calibration (ปรับความเร็วเชิงมุม)**

1. ทำเครื่องหมายทิศทางเริ่มต้นของหุ่นยนต์บนพื้น
2. สั่งให้หุ่นยนต์หมุนครบ 360 องศา (หรือหลายรอบเพื่อเพิ่มความแม่นยำ)
3. วัดมุมที่หมุนจริงด้วยสายตาหรือเครื่องวัดมุม
4. หากมุมจริงต่างจากค่าที่ตั้ง ให้ปรับค่า `wheel_separation` (ระยะห่างระหว่างล้อ)
5. ทำซ้ำจนกว่ามุมจริงจะใกล้เคียงค่าที่ตั้ง

> **หมายเหตุ:** ไม่ควรใช้ค่าจาก IMU เป็นเกณฑ์ในการ Calibrate Angular Velocity เพราะ IMU เองอาจมี Bias หรือ Drift การใช้การวัดทางกายภาพจริงให้ผลที่น่าเชื่อถือกว่า

### 10.3 Multi-machine Control (บทที่ 10)

ใช้ `ROS_DOMAIN_ID` แยกหุ่นยนต์แต่ละตัว

```bash
# หุ่นยนต์ตัวที่ 1
export ROS_DOMAIN_ID=1

# หุ่นยนต์ตัวที่ 2
export ROS_DOMAIN_ID=2
```

### 10.4 Robot Visual Interaction (บทที่ 11)

ตัวอย่างฟังก์ชันที่รองรับ (ต้องมี ROS-WiFi Camera Module)

- Color Tracking — ติดตามวัตถุตามสี
- Object Recognition and Tracking
- Face Recognition Tracking
- Autonomous Driving Line Patrol — ตามเส้น
- QR Code Motion Control — สั่งงานด้วย QR Code
- Gesture Control — ควบคุมด้วยท่าทาง
- Palm Control — ควบคุมด้วยฝ่ามือ

### 10.5 การพัฒนาเฟิร์มแวร์ ESP32

ตามบทที่ 15 ของหลักสูตร Yahboom

1. ติดตั้ง ESP-IDF
2. ติดตั้ง ESP32-microROS Components
3. แก้ไขซอร์สโค้ดในโปรเจกต์
4. Build ด้วยคำสั่ง `idf.py build`
5. แฟลชด้วย Flash Tool ของ Yahboom

---

## 11. การบำรุงรักษา

### 11.1 ก่อนใช้งานทุกครั้ง

- ตรวจสอบแรงดันแบตเตอรี่
- เช็คการเชื่อมต่อสายไฟทุกจุด
- ทดสอบเซ็นเซอร์เบื้องต้น

### 11.2 หลังใช้งานทุกครั้ง

- ปิดสวิตช์ก่อนถอดแบตเตอรี่
- เช็ดทำความสะอาดด้วยผ้าแห้ง
- เก็บในที่แห้ง อุณหภูมิห้อง

### 11.3 การชาร์จแบตเตอรี่

- ใช้ Charger ที่มากับชุดของ Yahboom เท่านั้น
- ห้ามชาร์จขณะหุ่นยนต์เปิดทำงาน
- ระวังอย่าให้แบตเตอรี่ลดต่ำกว่า 6.6V
- ห้ามทิ้งในที่ร้อนหรือแสงแดดโดยตรง

### 11.4 รอบการบำรุงรักษา

| รายการ | ความถี่ |
|---|---|
| ตรวจสายไฟและขั้วต่อ | ทุกสัปดาห์ |
| ขันสกรูล้อและโครงสร้าง | ทุกเดือน |
| ทำความสะอาดเลนส์ Lidar | ทุกเดือน |
| Calibrate IMU | ทุก 3 เดือน |
| อัปเดตเฟิร์มแวร์ | ตามที่ Yahboom ประกาศ |

---

## 12. การแก้ไขปัญหาเบื้องต้น

### 12.1 ตารางอาการและการแก้ไข

| อาการ | สาเหตุที่เป็นไปได้ | วิธีแก้ไข |
|---|---|---|
| หุ่นยนต์ไม่เปิด | แบตเตอรี่หมด, สวิตช์เสีย | ชาร์จแบตเตอรี่, ตรวจสายไฟ |
| เชื่อม WiFi ไม่ได้ | ตั้งค่า WiFi ผิด | รีเซ็ตการตั้งค่า WiFi ของ ESP32 |
| `ros2 topic list` ไม่เห็น Topic | ROS_DOMAIN_ID ไม่ตรง, VM ไม่ใช่ Bridged | ตรวจ ROS_DOMAIN_ID และ Network Mode |
| micro-ROS Agent ไม่ขึ้น | ยังไม่รัน Agent | รัน `ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888` |
| ล้อหมุนทิศตรงข้าม | สายมอเตอร์สลับ | สลับสายขั้ว |
| Lidar ไม่ส่งข้อมูล | สายหลวม, Driver ไม่โหลด | ตรวจสายและรีสตาร์ต Node |
| IMU แสดงค่าผิดเพี้ยน | ยังไม่ Calibrate | รัน Calibration Script |
| หุ่นยนต์เลี้ยวไม่ตรง | Encoder ผิด, Parameter ผิด | Calibrate Linear/Angular Velocity |
| Map เพี้ยน/ไม่ตรง | ขับเร็วเกินไป, Loop Closure ไม่ทำงาน, พื้นผิวสะท้อนแสง, IMU ยังไม่ Calibrate | ขับช้าลง, Calibrate IMU, หลีกเลี่ยงพื้นกระจกหรือพื้นสะท้อน, กลับมาที่จุดเริ่มต้นเพื่อปิด Loop |
| Docker เข้าไม่ได้ | Container ไม่ได้เริ่ม | `docker start <container_name>` |

### 12.2 คำสั่งวินิจฉัยที่มีประโยชน์

```bash
# ดู Node ทั้งหมด
ros2 node list

# รายละเอียดของ Node
ros2 node info /node_name

# ความถี่ของ Topic
ros2 topic hz /scan

# ดูข้อความล่าสุด
ros2 topic echo /imu --once

# ตรวจ TF Tree
ros2 run tf2_tools view_frames

# ดู Log
ros2 log view
```

### 12.3 ช่องทางขอความช่วยเหลือจาก Yahboom

- **อีเมล:** support@yahboom.com
- **WhatsApp:** +86 18682378128
- **เว็บไซต์:** https://www.yahboom.net/study/MicroROS-ESP32
- **GitHub Issues:** https://github.com/YahboomTechnology/Mirco-Ros-Car_VM/issues

---

## 13. ความปลอดภัย

### 13.1 ข้อควรระวัง

- ห้ามใช้งานในสภาพแวดล้อมที่มีน้ำหรือความชื้นสูง
- ห้ามใช้งานใกล้แหล่งความร้อน
- หลีกเลี่ยงการชนกับวัตถุแข็ง
- อย่ามองเลเซอร์ Lidar โดยตรง
- ปิดเครื่องก่อนเปลี่ยนชิ้นส่วน

### 13.2 ความปลอดภัยของแบตเตอรี่

- ใช้แบตเตอรี่ที่มากับชุด Yahboom เท่านั้น
- หากแบตบวมหรือร้อนผิดปกติ ให้หยุดใช้และเก็บในที่ปลอดภัย
- ห้ามทิ้งในกองไฟหรือถังขยะทั่วไป
- ห้ามแกะหรือเจาะแบตเตอรี่

### 13.3 ความปลอดภัยทางไฟฟ้า

- ตรวจสอบขั้ว + และ - ก่อนเชื่อมต่อ
- อย่าลัดวงจรขั้วแบตเตอรี่
- ตัดไฟก่อนซ่อมหรือเปลี่ยนสาย

---

## 14. ภาคผนวก

### 14.1 คำศัพท์ที่ควรรู้

| คำศัพท์ | คำเต็ม | คำอธิบาย |
|---|---|---|
| IMU | Inertial Measurement Unit | หน่วยวัดแรงเฉื่อย |
| Lidar | Light Detection and Ranging | เซ็นเซอร์วัดระยะด้วยเลเซอร์ |
| TOF | Time of Flight | หลักการวัดระยะจากเวลาของแสง |
| SLAM | Simultaneous Localization and Mapping | สร้างแผนที่และระบุตำแหน่งพร้อมกัน |
| ROS | Robot Operating System | เฟรมเวิร์กพัฒนาหุ่นยนต์ |
| micro-ROS | - | ROS2 สำหรับไมโครคอนโทรลเลอร์ |
| Odometry | - | การประมาณตำแหน่งจาก Encoder + IMU |
| Node | - | หน่วยประมวลผลย่อยใน ROS2 |
| Topic | - | ช่องทางส่งข้อความระหว่าง Node |
| Encoder | - | ตัวนับรอบของมอเตอร์ |
| UDP | User Datagram Protocol | โปรโตคอลส่งข้อมูลแบบไม่ยืนยัน |
| VM | Virtual Machine | เครื่องเสมือน |

### 14.2 แหล่งอ้างอิงทางการของ Yahboom

| แหล่ง | URL |
|---|---|
| GitHub Repository | https://github.com/YahboomTechnology/Mirco-Ros-Car_VM |
| เอกสารหลักสูตร | https://www.yahboom.net/study/MicroROS-ESP32 |
| หน้าผลิตภัณฑ์ | https://category.yahboom.net/products/microros-esp32 |
| Technical Support | support@yahboom.com |

### 14.3 แหล่งอ้างอิงเพิ่มเติม

| แหล่ง | URL |
|---|---|
| micro-ROS Official | https://micro.ros.org |
| ROS2 Documentation | https://docs.ros.org/en/humble/ |
| Nav2 Documentation | https://navigation.ros.org/ |
| OpenCV | https://opencv.org |
| MediaPipe | https://mediapipe.dev |

### 14.4 รายการ Contact และผู้รับผิดชอบ (ทีมของเรา)

> หมายเหตุ: ส่วนนี้ให้ทีมเติมเอง

| บทบาท | ชื่อ | ช่องทางติดต่อ |
|---|---|---|
| หัวหน้าทีม | _____________ | _____________ |
| ผู้ดูแลฮาร์ดแวร์ | _____________ | _____________ |
| ผู้ดูแลซอฟต์แวร์ | _____________ | _____________ |
| ผู้ดูแลเอกสาร | _____________ | _____________ |

### 14.5 บันทึกการแก้ไขเอกสาร

| เวอร์ชัน | วันที่ | ผู้แก้ไข | หมายเหตุ |
|---|---|---|---|
| 1.0 | ____________ | ____________ | จัดทำเอกสารฉบับแรก |

---

**สิ้นสุดคู่มือ**

> หากพบข้อผิดพลาดในเอกสารหรือต้องการเสนอแนะปรับปรุง โปรดแจ้งผู้ดูแลเอกสาร
> เอกสารนี้อ้างอิงข้อมูลทางการของ Yahboom Technology ณ เวอร์ชัน ROS2-Humble และอาจมีการเปลี่ยนแปลงตามรุ่นและการอัปเดต

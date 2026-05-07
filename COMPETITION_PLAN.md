# Competition Plan — Autonomous Robot Navigation
**ช่วงเวลา: 5–29 พ.ค. 2026**

---

## ภาพรวม Mission Sequence

```
START → survivor_1 (ตรวจคน + ปล่อยกล่อง)
      → scan_1 (อ่าน AprilTag)
      → scan_2 (อ่าน AprilTag)
      → survivor_2 (ตรวจคน + ปล่อยกล่อง)
      → HOME
```

---

## ~~สัปดาห์ที่ 1 (5–11 พ.ค.) — ตั้งค่า Waypoints~~ ✅ เสร็จแล้ว

**เป้าหมาย:** บันทึก waypoint ทุกจุดในสนามจริง

| จุด | ประเภท | หมายเหตุ |
|-----|--------|----------|
| `scan_1` | AprilTag reading | จุดอ่าน Tag แรก |
| `scan_2` | AprilTag reading | จุดอ่าน Tag สอง |
| `survivor_1` | พื้นที่ผู้ประสบภัย | ตรวจคน + ปล่อยกล่อง |
| `survivor_2` | พื้นที่ผู้ประสบภัย | ตรวจคน + ปล่อยกล่อง |
| `HOME` | จุดเริ่มต้น | ตำแหน่งกลับบ้าน |

**งาน:**
- [x] ใช้ `get_waypoint.py` บันทึกตำแหน่งทุกจุดที่สนามจริง
- [x] อัปเดต `nav_waypoints.yaml` ให้ครบทุก waypoint

---

## สัปดาห์ที่ 2 (12–18 พ.ค.) — สร้าง Autonomous Mission Script

**เป้าหมาย:** รวม navigation + AprilTag + servo drop เป็น script เดียว ไม่ต้องมีคนควบคุม

**งาน:**
- [ ] แก้ `mission_script.py` — เปลี่ยนจาก `input()` เป็น hardcode sequence อัตโนมัติ
- [ ] เพิ่ม **timeout** กรณี AprilTag ไม่เจอ (ไม่ให้หยุดรอนาน)
- [ ] เพิ่ม **retry** กรณี navigation failed

---

## สัปดาห์ที่ 3 (19–25 พ.ค.) — ทดสอบและปรับแต่ง

**เป้าหมาย:** ระบบเสถียรพร้อมแข่ง

**งาน:**
- [ ] ซ้อม run เต็มรอบ **≥5 ครั้ง/วัน**
- [ ] ปรับ Nav2 parameters ใน `dwb_nav_params.yaml` / `rpp_nav_params.yaml`
- [ ] ทดสอบ **WiFi interference** — ต้องต่อผ่าน WiFi 2.4GHz ที่ผู้จัดเตรียม (กฎข้อ 3.4)

---

## สัปดาห์ที่ 4 (26–29 พ.ค.) — Final Prep

**เป้าหมาย:** พร้อม 100% วันแข่ง

**งาน:**
- [ ] Plan B: ถ้า nav ล้มเหลว → restart ให้ได้ **mini-bingo อย่างน้อย (+20 คะแนน)**
- [ ] เตรียม launch script — run ได้ด้วยคำสั่งเดียว

---

## ไฟล์สำคัญ

| ไฟล์ | หน้าที่ |
|------|---------|
| `get_waypoint.py` | บันทึก waypoint จากสนามจริง |
| `nav_waypoints.yaml` | เก็บพิกัด waypoint ทั้งหมด |
| `mission_script.py` | autonomous mission sequence |
| `dwb_nav_params.yaml` | Nav2 DWB controller params |
| `rpp_nav_params.yaml` | Nav2 RPP controller params |
| `nav2_launch.py` | launch file หลัก |

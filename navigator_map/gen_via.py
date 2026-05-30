#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ช่วยทำ via สวยๆ วันแข่ง — เติมทิศ via อัตโนมัติ + เช็คระยะห่างกำแพง

วิธีใช้ (วันแข่ง):
  1. แก้ x,y ของ waypoint/via ใน nav_waypoints.yaml (พิมพ์แค่ตำแหน่ง ไม่ต้องใส่ orientation ของ via)
     - via แต่ละจุด ใส่แค่:   - {x: 1.5, y: -0.92}
  2. python3 gen_via.py            # เติมทิศ via (หันไปจุดถัดไป) + เช็คชนกำแพง + วาดรูป
  3. ดู docs/wp_overlay.png ว่าเส้นสวย/ไม่ชนไหม ถ้าไม่โอเคแก้ x,y แล้วรันซ้ำ

กฎ via สวย (ที่สคริปต์นี้ช่วย):
  - ทิศ via = หันไปจุดถัดไปเสมอ (สคริปต์เติมให้)
  - มุมฉาก: ให้ x หรือ y ของ via ที่ติดกันตรงกัน (เช่น 1.5,-0.52 -> 1.5,-0.92 = ดิ่งตรง)
  - เข้ากระเป๋าตรงด้านที่เปิด, เดินในช่องว่าง, ห่างกำแพง >= MARGIN (สคริปต์เตือนถ้าชิด)
ทิศของ waypoint หลัก (ไม่ใช่ via) สคริปต์ "ไม่แตะ" — ตั้งเองตามภารกิจ (หันเข้ากระเป๋า/หา tag)
"""
import math
import sys
import yaml
import numpy as np
from PIL import Image

WP = sys.argv[1] if len(sys.argv) > 1 else "nav_waypoints.yaml"
MARGIN = 0.18          # ระยะห่างกำแพงขั้นต่ำ (m) ~ หุ่นครึ่งตัว+pad
SQUARE_TOL = 0.06      # เยื้อง <= นี้ (m) ในแกน x/y -> จัดให้ตรง (ฉาก)
RES, OX, OY = 0.05, -0.387, -2.54

def quat(yaw):
    return round(math.sin(yaw / 2), 5), round(math.cos(yaw / 2), 5)

# โหลด map สำหรับเช็คระยะกำแพง
img = np.array(Image.open("my_robot_map.pgm"))
H, W = img.shape
wall_r, wall_c = np.where(img == 0)
def wall_dist(x, y):
    col = (x - OX) / RES
    row = (H - 1) - (y - OY) / RES
    return np.min(np.hypot(wall_r - row, wall_c - col)) * RES

doc = yaml.safe_load(open(WP))
wps = doc["waypoints"]

# ---- auto-square: จัด via ที่เกือบฉากให้ตรงเป๊ะ (ขยับเฉพาะ via) ----
# segment ไหนเกือบแนวตั้ง (|dx|<=tol) -> จับ 2 จุดให้ x เท่ากัน; เกือบแนวนอน -> y เท่ากัน
# ใช้ union-find รวมจุดที่ x (หรือ y) ควรเท่ากันเป็นกลุ่ม แล้วตั้งค่าร่วม
#   - กลุ่มที่มี waypoint (fixed) -> ใช้ค่า waypoint;  ไม่มี -> ใช้ค่าเฉลี่ย
# ทำให้ via 2 จุดที่ควรตรงกันไม่ "สลับค่า" กันเอง
def _square(chain, fixed):
    n = len(chain)
    px = list(range(n)); py = list(range(n))
    def find(p, i):
        while p[i] != i:
            p[i] = p[p[i]]; i = p[i]
        return i
    def union(p, a, b):
        p[find(p, a)] = find(p, b)
    for i in range(n - 1):
        ax, ay = chain[i]; bx, by = chain[i + 1]
        dx, dy = abs(ax - bx), abs(ay - by)
        if dx <= SQUARE_TOL and dx <= dy:        # แนวตั้ง -> x เท่ากัน
            union(px, i, i + 1)
        elif dy <= SQUARE_TOL and dy < dx:       # แนวนอน -> y เท่ากัน
            union(py, i, i + 1)
    out = list(chain)
    for parent, axis in ((px, 0), (py, 1)):
        groups = {}
        for i in range(n):
            groups.setdefault(find(parent, i), []).append(i)
        for members in groups.values():
            if len(members) < 2:
                continue
            fx = [chain[i][axis] for i in members if i in fixed]
            target = (sum(fx) / len(fx)) if fx else (sum(chain[i][axis] for i in members) / len(members))
            target = round(target, 3)
            for i in members:
                if i not in fixed:
                    out[i] = (target, out[i][1]) if axis == 0 else (out[i][0], target)
    return out

print("=== auto-square via (เยื้อง <= {:.0f}cm จัดให้ตรง) ===".format(SQUARE_TOL * 100))
sq_changes = 0
prev_wp = None
for wp in wps:
    vias = wp.get("via", [])
    if vias:
        chain = ([(prev_wp["x"], prev_wp["y"])] if prev_wp else []) \
                + [(v["x"], v["y"]) for v in vias] + [(wp["x"], wp["y"])]
        offset = 1 if prev_wp else 0
        fixed = {i for i in range(len(chain)) if i < offset or i == len(chain) - 1}
        new = _square(chain, fixed)
        for i, v in enumerate(vias):
            cx0, cy0 = chain[offset + i]; nx0, ny0 = new[offset + i]
            if (round(nx0, 3), round(ny0, 3)) != (round(cx0, 3), round(cy0, 3)):
                print(f"  {wp['task']} via#{i+1}: ({cx0:.3f},{cy0:.3f}) -> ({nx0:.3f},{ny0:.3f})")
                v["x"], v["y"] = round(nx0, 3), round(ny0, 3)
                sq_changes += 1
    prev_wp = wp
print(f"จัดฉาก {sq_changes} จุด\n" if sq_changes else "ไม่มีจุดต้องจัด (ฉากอยู่แล้ว)\n")

# เติมทิศ via: หันไปจุดถัดไป (via ถัดไป หรือ waypoint)
prev = None
warns = []
for wp in wps:
    target = (wp["x"], wp["y"])
    seq = wp.get("via", []) + [None]      # None = waypoint เอง
    for i, v in enumerate(wp.get("via", [])):
        nxt = (wp["via"][i + 1]["x"], wp["via"][i + 1]["y"]) if i + 1 < len(wp["via"]) else target
        yaw = math.atan2(nxt[1] - v["y"], nxt[0] - v["x"])
        z, w = quat(yaw)
        v["orientation"] = {"z": z, "w": w}
        d = wall_dist(v["x"], v["y"])
        tag = "  <-- ชิดกำแพง!" if d < MARGIN else ""
        print(f"  via ({v['x']:.2f},{v['y']:.2f}) ทิศ {math.degrees(yaw):+.0f}°  ห่างกำแพง {d:.2f}m{tag}")
        if d < MARGIN:
            warns.append((wp["task"], v["x"], v["y"], d))
    # HOME (ไม่มี type = ไม่มีภารกิจ) -> ตั้งทิศหันตามทางที่วิ่งเข้ามา (จุดก่อนถึงมัน)
    # waypoint ที่มี type (person/tag) ไม่แตะ — ทิศหันเข้ากระเป๋า/หา tag ตั้งมือเอง
    if "type" not in wp:
        inc = (wp["via"][-1]["x"], wp["via"][-1]["y"]) if wp.get("via") else prev
        if inc is not None:
            yaw = math.atan2(target[1] - inc[1], target[0] - inc[0])
            z, w = quat(yaw)
            wp["orientation"] = {"z": z, "w": w}
            print(f"{wp['task']:11s} ตั้งทิศหัน {math.degrees(yaw):+.0f}° (ตามทางวิ่งเข้ามา)")
    # เช็ค waypoint หลัก (ไม่แก้ทิศ) — เตือนเฉพาะจุดในที่โล่ง (ไม่มี type เช่น HOME)
    # wp ที่มี type (person/tag) ตั้งใจอยู่ในกระเป๋า ชิดกำแพงปกติ ไม่เตือน
    d = wall_dist(*target)
    in_pocket = "type" in wp
    tag = "  (ในกระเป๋า)" if in_pocket else ("  <-- ชิดกำแพง!" if d < MARGIN else "")
    print(f"{wp['task']:11s} ({target[0]:.2f},{target[1]:.2f})  ห่างกำแพง {d:.2f}m{tag}")
    if d < MARGIN and not in_pocket:
        warns.append((wp["task"], target[0], target[1], d))
    prev = target

# เขียนกลับ
yaml.safe_dump(doc, open(WP, "w"), sort_keys=False, allow_unicode=True, default_flow_style=False)
print(f"\nเติมทิศ via + เขียนกลับ {WP} แล้ว")
if warns:
    print(f"!! เตือน {len(warns)} จุดชิดกำแพง < {MARGIN}m — ขยับ x,y ให้ห่างขึ้น:")
    for t, x, y, d in warns:
        print(f"   {t}: ({x:.2f},{y:.2f}) ห่างแค่ {d:.2f}m")
else:
    print("ทุกจุดห่างกำแพงพอ ✓")

# วาดรูป
import subprocess
subprocess.run([sys.executable, "draw_waypoints.py", WP, "docs/wp_overlay.png"])
print("ดูรูป: docs/wp_overlay.png")

#!/usr/bin/env python3
# watch_pose.py — มอนิเตอร์เบาๆ ไว้เช็ก "แมพหมุน/หลุด" ตอนแข่ง (แทน RViz ที่กิน CPU)
#
# วันแข่งปิด RViz (OPEN_RVIZ=false) จะไม่เห็นด้วยตาว่า localization เพี้ยนไหม
# สคริปต์นี้อ่าน TF map->base_link (ตัวเดียวกับที่ RViz ใช้วาดหุ่นบนแมพ) ทุก ~0.5s
# แล้ว "เตือนเด้ง" เมื่อ yaw หมุน/ตำแหน่งกระโดดเอง ทั้งที่ไม่ได้สั่งวิ่ง = แมพหลุด
#
# ทำไมใช้ TF ไม่ใช้ /amcl_pose: amcl publish /amcl_pose เฉพาะตอนหุ่นขยับเกิน
# update_min_d/a — พอหุ่นจอด (ปล่อยกล่อง/สแกน tag/HOME) มันเงียบเป็นปกติ จะเตือนหลอก.
# ส่วน TF map->base_link ถูก rebroadcast ทุก laser scan แม้หุ่นจอด → สดตลอด เช็กได้จริง.
#
# วิธีใช้ (เปิด terminal ที่ 4 ตอน nav2 รันอยู่ ใน domain เดียวกัน):
#   cd navigator_map && python3 watch_pose.py
#
# ไฟเขียว = แมพโอเค / แดง = แมพหมุน-กระโดดเอง หรือ TF ค้าง (amcl/scan ตาย)

import math
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from geometry_msgs.msg import Twist
from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

# --- เกณฑ์เตือน ---
PRINT_PERIOD_SEC = 0.5        # อ่าน TF + พิมพ์สถานะทุกกี่วินาที
SPIN_RATE_WARN = 0.30         # |yaw rate| (rad/s) ที่ถือว่า "หมุนเร็ว"
JUMP_WARN_M = 0.15            # ตำแหน่งกระโดด (เมตร) ระหว่างรอบที่ถือว่าผิดปกติ
CMD_IDLE = 0.05               # |cmd_vel| ต่ำกว่านี้ = "ไม่ได้สั่ง"
CMD_FRESH_SEC = 0.6           # /cmd_vel เก่ากว่านี้ถือว่าไม่มีคำสั่ง (กัน latch ค้างค่าเก่า)
TF_FROZEN_SEC = 2.0           # stamp ของ TF ไม่ขยับเกินนี้ = TF ค้าง (amcl/scan ตาย)

RED = "\033[91m"; GREEN = "\033[92m"; DIM = "\033[2m"; RESET = "\033[0m"


def yaw_from_quat(q):
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class PoseWatcher(Node):
    def __init__(self):
        super().__init__('watch_pose')

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_subscription(Twist, '/cmd_vel', self.cmd_cb, 10)

        # cmd_vel ล่าสุด + เวลาที่รับ (ไว้ทำ recency gate)
        self.cmd_w = 0.0
        self.cmd_v = 0.0
        self.last_cmd_t = 0.0

        # สำหรับคำนวณ rate/jump เทียบรอบก่อน
        self.prev_yaw = None
        self.prev_xy = None
        self.prev_t = None

        # ไว้เช็ก TF ค้าง: เวลา (wall) ที่ stamp ของ TF เปลี่ยนล่าสุด
        self.last_stamp_ns = None
        self.last_stamp_change_t = None

        self.create_timer(PRINT_PERIOD_SEC, self.tick)
        print(f"{DIM}watch_pose: รอ TF map->base_link ... (Ctrl-C เพื่อออก){RESET}")

    def cmd_cb(self, msg):
        self.cmd_w = msg.angular.z
        self.cmd_v = msg.linear.x
        self.last_cmd_t = time.time()

    def tick(self):
        now = time.time()

        # อ่าน TF ล่าสุด (Time() = latest available)
        try:
            tf = self.tf_buffer.lookup_transform('map', 'base_link', Time())
        except TransformException as e:
            print(f"{DIM}รอ TF map->base_link ... ({e}){RESET}")
            return

        yaw = yaw_from_quat(tf.transform.rotation)
        xy = (tf.transform.translation.x, tf.transform.translation.y)

        # --- เช็ก TF ค้าง: ดูว่า stamp ขยับไหม (ไม่พึ่งนาฬิกาสัมบูรณ์ กันปัญหา clock skew) ---
        stamp_ns = Time.from_msg(tf.header.stamp).nanoseconds
        if stamp_ns != self.last_stamp_ns:
            self.last_stamp_ns = stamp_ns
            self.last_stamp_change_t = now
        stale = (now - self.last_stamp_change_t) > TF_FROZEN_SEC

        # --- คำนวณ yaw rate + การกระโดด เทียบรอบก่อน ---
        yaw_rate = 0.0
        jump = 0.0
        if self.prev_t is not None:
            dt = now - self.prev_t
            if dt > 1e-3:
                dyaw = math.atan2(math.sin(yaw - self.prev_yaw), math.cos(yaw - self.prev_yaw))
                yaw_rate = dyaw / dt
                jump = math.hypot(xy[0] - self.prev_xy[0], xy[1] - self.prev_xy[1])
        self.prev_yaw = yaw
        self.prev_xy = xy
        self.prev_t = now

        # --- cmd_vel แบบ recency: ถ้าไม่มีคำสั่งสดๆ ถือว่า "ไม่ได้สั่ง" (=0) กัน latch ---
        cmd_fresh = (now - self.last_cmd_t) < CMD_FRESH_SEC
        eff_w = self.cmd_w if cmd_fresh else 0.0
        eff_v = self.cmd_v if cmd_fresh else 0.0

        # หมุน/กระโดดเอง = ขยับเร็วทั้งที่ไม่ได้สั่ง (ตอน stale ค่าค้าง งดเตือน กันหลอก)
        spinning_self = (not stale) and abs(yaw_rate) > SPIN_RATE_WARN and abs(eff_w) < CMD_IDLE
        jumping_self = (not stale) and jump > JUMP_WARN_M and abs(eff_v) < CMD_IDLE

        flags = []
        color = GREEN
        if stale:
            flags.append(f"TF ค้าง >{TF_FROZEN_SEC:.0f}s (amcl/scan ตาย?)")
            color = RED
        if spinning_self:
            flags.append(f"!! แมพหมุนเอง yaw_rate={yaw_rate:+.2f} rad/s (ไม่ได้สั่งหมุน)")
            color = RED
        if jumping_self:
            flags.append(f"!! ตำแหน่งกระโดด {jump:.2f}m (ไม่ได้สั่งวิ่ง)")
            color = RED

        deg = math.degrees(yaw)
        msg = (f"pos=({xy[0]:+.2f},{xy[1]:+.2f}) yaw={deg:+6.1f}° "
               f"rate={yaw_rate:+.2f} cmd(v={eff_v:+.2f},w={eff_w:+.2f})")
        tail = ("  " + " | ".join(flags)) if flags else "  แมพโอเค"
        print(f"{color}{msg}{tail}{RESET}")


def main():
    rclpy.init()
    node = PoseWatcher()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():            # SIGTERM ทำให้ context ปิดไปแล้ว — อย่าเรียกซ้ำ
            rclpy.shutdown()


if __name__ == '__main__':
    main()

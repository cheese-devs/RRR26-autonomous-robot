#!/usr/bin/env python3
# ทดสอบ exit_pocket() แบบแยก — ไป wp → หมุนเลียน mission → clearCostmap → backup(0.30m)
# log: accepted, result, เวลาใช้, ระยะถอยจริงจาก odom
# Usage: python3 test_backup.py [wp1|wp4]   (default: wp1)
import rclpy
import sys
import time
import math
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry

# ใช้ค่าเดียวกับ navigator_script.exit_pocket()
POCKET_BACKUP_DIST_M      = 0.30
POCKET_BACKUP_SPEED_MPS   = 0.05
POCKET_BACKUP_TIMEOUT_SEC = 8
CLEAR_SETTLE_SEC          = 1.0

# จาก nav_waypoints.yaml
WAYPOINTS = {
    'wp1': {
        'goal': {'x': 0.681, 'y': -0.357, 'qz': -0.74625, 'qw': 0.66566},
        'via': [],
    },
    'wp4': {
        'goal': {'x': 0.705, 'y': -1.730, 'qz': 0.5531, 'qw': 0.83311},
        'via': [{'x': 2.672, 'y': -2.06, 'qz': 0.9357, 'qw': -0.35279}],
    },
}

# spin เลียนแบบ mission (warmup + หมุนหาเป้า)
SPIN_SPEED_RAD = 0.5      # rad/s
SPIN_DURATION  = 12.0     # ~2 รอบ ที่ 0.5 rad/s


class BackupTester:
    def __init__(self):
        self.nav = BasicNavigator()
        self.cmd_vel_pub = self.nav.create_publisher(Twist, '/cmd_vel', 10)
        self.odom_xy = None
        self.nav.create_subscription(Odometry, '/odom', self._odom_cb, 10)

    def _odom_cb(self, msg):
        p = msg.pose.pose.position
        self.odom_xy = (p.x, p.y)

    def make_pose(self, x, y, qz, qw):
        ps = PoseStamped()
        ps.header.frame_id = 'map'
        ps.header.stamp = self.nav.get_clock().now().to_msg()
        ps.pose.position.x = x
        ps.pose.position.y = y
        ps.pose.orientation.z = qz
        ps.pose.orientation.w = qw
        return ps

    def goto(self, x, y, qz, qw, label):
        print(f"   goToPose {label} ({x:.2f}, {y:.2f}) ...")
        self.nav.clearAllCostmaps()
        time.sleep(CLEAR_SETTLE_SEC)
        self.nav.goToPose(self.make_pose(x, y, qz, qw))
        t0 = time.time()
        while not self.nav.isTaskComplete():
            time.sleep(0.2)
            if time.time() - t0 > 120:
                print(f"   [!] timeout ไป {label}")
                self.nav.cancelTask()
                return False
        result = self.nav.getResult()
        ok = (result == TaskResult.SUCCEEDED)
        print(f"   {label} result = {result} ({'OK' if ok else 'FAIL'})")
        return ok

    def spin(self):
        print(f"[2/4] spin {SPIN_SPEED_RAD} rad/s × {SPIN_DURATION}s เลียนแบบ mission...")
        twist = Twist()
        twist.angular.z = SPIN_SPEED_RAD
        t0 = time.time()
        while time.time() - t0 < SPIN_DURATION:
            self.cmd_vel_pub.publish(twist)
            time.sleep(0.1)
        # หยุด
        zero = Twist()
        for _ in range(5):
            self.cmd_vel_pub.publish(zero)
            time.sleep(0.05)
        print("   หมุนเสร็จ")

    def backup_test(self):
        print(f"[3/4] clearAllCostmaps + sleep {CLEAR_SETTLE_SEC}s")
        self.nav.clearAllCostmaps()
        time.sleep(CLEAR_SETTLE_SEC)

        start_xy = self.odom_xy
        print(f"[4/4] backup({POCKET_BACKUP_DIST_M}m @ {POCKET_BACKUP_SPEED_MPS}m/s, "
              f"timeout {POCKET_BACKUP_TIMEOUT_SEC}s)")
        print(f"   odom เริ่ม: {start_xy}")

        t0 = time.time()
        accepted = self.nav.backup(
            backup_dist=POCKET_BACKUP_DIST_M,
            backup_speed=POCKET_BACKUP_SPEED_MPS,
            time_allowance=POCKET_BACKUP_TIMEOUT_SEC,
        )
        print(f"   accepted = {accepted}")
        if accepted is False:
            print("   >>> RESULT: REJECTED ก่อนเริ่ม (behavior_server ไม่รับ goal)")
            return

        while not self.nav.isTaskComplete():
            time.sleep(0.1)
        elapsed = time.time() - t0
        result = self.nav.getResult()
        end_xy = self.odom_xy
        dist = 0.0
        if start_xy and end_xy:
            dist = math.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])

        print(f"   result = {result}")
        print(f"   เวลาใช้ = {elapsed:.2f}s")
        print(f"   odom จบ: {end_xy}")
        print(f"   ระยะถอยจริง = {dist:.3f}m (ตั้งใจ {POCKET_BACKUP_DIST_M}m)")
        if result == TaskResult.SUCCEEDED:
            print("   >>> RESULT: SUCCEEDED")
        elif result == TaskResult.FAILED:
            print("   >>> RESULT: FAILED — อาจ collision check ปฏิเสธ / timeout / TF ขาด")
        elif result == TaskResult.CANCELED:
            print("   >>> RESULT: CANCELED")
        else:
            print(f"   >>> RESULT: {result}")


def main():
    wp_name = sys.argv[1] if len(sys.argv) > 1 else 'wp1'
    if wp_name not in WAYPOINTS:
        print(f"unknown waypoint: {wp_name}  (เลือก: {list(WAYPOINTS.keys())})")
        sys.exit(1)
    wp = WAYPOINTS[wp_name]

    rclpy.init()
    print(f"=== TEST exit_pocket() @ {wp_name} ===")
    print("รอ Nav2 active...")
    tester = BackupTester()
    tester.nav.waitUntilNav2Active()
    print("Nav2 active แล้ว\n")

    try:
        print(f"[1/4] นำทางไป {wp_name} ({len(wp['via'])} via points)")
        for i, v in enumerate(wp['via']):
            if not tester.goto(v['x'], v['y'], v['qz'], v['qw'], f"via[{i}]"):
                print(f"ไป via[{i}] ไม่สำเร็จ — ยกเลิกเทส")
                return
        g = wp['goal']
        if not tester.goto(g['x'], g['y'], g['qz'], g['qw'], wp_name):
            print(f"ไป {wp_name} ไม่สำเร็จ — ยกเลิกเทส")
            return
        time.sleep(1.0)
        tester.spin()
        time.sleep(0.5)
        tester.backup_test()
    except KeyboardInterrupt:
        print("\n[INT] ยกเลิก")
        tester.nav.cancelTask()
        zero = Twist()
        for _ in range(5):
            tester.cmd_vel_pub.publish(zero)
            time.sleep(0.05)
    finally:
        # ไม่เรียก lifecycleShutdown() — ปล่อย Nav2 ทำงานต่อ จะได้รันเทสซ้ำได้
        rclpy.shutdown()


if __name__ == "__main__":
    main()

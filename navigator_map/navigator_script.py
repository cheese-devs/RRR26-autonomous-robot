import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped
import yaml
import time
import subprocess
import os
import threading

NAV_RETRY = 2          # จำนวนครั้งที่ retry เมื่อ nav ล้มเหลว
YAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nav_waypoints.yaml')


class MissionRunner:
    def __init__(self):
        self.nav = BasicNavigator()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

    def _run_script(self, script_name):
        path = os.path.join(self.script_dir, script_name)
        print(f"   -> รัน: {script_name}")
        try:
            subprocess.run(["python3", path], check=True)
            print("   -> เสร็จสิ้น")
        except subprocess.CalledProcessError as e:
            print(f"   -> [ERROR] {e}")
        except FileNotFoundError:
            print(f"   -> [ERROR] ไม่พบไฟล์: {path}")

    def _perform_task(self, wp):
        wp_type = wp.get('type', 'h')
        name = wp['task']
        print(f"--- ถึงจุด {name} (type={wp_type}) ---")
        if wp_type == 'a':
            self._run_script("apriltag_script.py")
        elif wp_type == 's':
            self._run_script("mission_script.py")
        else:
            time.sleep(2)
        print(f"--- เสร็จสิ้นภารกิจที่ {name} ---\n")

    def _go_to(self, wp):
        """นำทางไปยัง waypoint พร้อม retry — คืนค่า True ถ้าถึงจุดหมาย"""
        for attempt in range(1, NAV_RETRY + 2):
            goal = PoseStamped()
            goal.header.frame_id = 'map'
            goal.header.stamp = self.nav.get_clock().now().to_msg()
            goal.pose.position.x = wp['x']
            goal.pose.position.y = wp['y']
            goal.pose.orientation.z = wp['orientation']['z']
            goal.pose.orientation.w = wp['orientation']['w']

            print(f">> มุ่งหน้าไป: {wp['task']} (ครั้งที่ {attempt})")
            self.nav.goToPose(goal)
            start = time.time()
            last_log = start
            while not self.nav.isTaskComplete():
                time.sleep(0.1)
                now = time.time()
                if now - last_log >= 5.0:
                    print(f"   [NAV] รออยู่... ({int(now - start)} วิ)")
                    last_log = now

            result = self.nav.getResult()
            if result == TaskResult.SUCCEEDED:
                return True
            elif result == TaskResult.CANCELED:
                print(f"   [CANCELED] ยกเลิกการเดินทางไป {wp['task']}")
                return False
            else:
                print(f"   [FAILED] ไปไม่ถึง {wp['task']}" +
                      (f" — retry {attempt}/{NAV_RETRY}" if attempt <= NAV_RETRY else ""))

        print(f"   [SKIP] ข้าม {wp['task']} หลัง retry ครบ {NAV_RETRY} ครั้ง")
        return False

    def run(self):
        with open(YAML_PATH, 'r') as f:
            waypoints = yaml.safe_load(f)['waypoints']

        print("กำลังรอให้ Nav2 พร้อมใช้งาน...")
        done = threading.Event()
        def _wait():
            try:
                self.nav.waitUntilNav2Active()
            finally:
                done.set()
        t = threading.Thread(target=_wait, daemon=True)
        t.start()
        if not done.wait(timeout=15.0):
            print("[WARN] waitUntilNav2Active หมดเวลา — ดำเนินการต่อเลย")
        print("[INFO] Nav2 ready")

        print(f"\n=== เริ่ม Mission ({len(waypoints)} จุด) ===\n")
        for wp in waypoints:
            if self._go_to(wp):
                self._perform_task(wp)

        print("\n[DONE] Mission เสร็จสิ้น!")


def main():
    rclpy.init()
    runner = MissionRunner()
    try:
        runner.run()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] หยุดโปรแกรม")
    finally:
        rclpy.shutdown()


if __name__ == '__main__':
    main()

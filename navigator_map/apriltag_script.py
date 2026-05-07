import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
import subprocess
import os
import signal
import time
import math
import threading

class AprilTagScanner(Node):
    def __init__(self):
        super().__init__('apriltag_scanner')
        self.pub_cmd = self.create_publisher(Twist, '/cmd_vel', 10)
        self.sub_tag = self.create_subscription(
            String, '/vision/latest_at_id', self.tag_callback, 10)

        self.timeout_sec   = 6.0
        self.max_rotations = 8  # 8 * 45° = 360°
        self.rotation_count = 0
        self.found = False

        self.timer = self.create_timer(self.timeout_sec, self.timeout_callback)
        self.get_logger().info("เริ่มสแกนหา AprilTag...")

    def _stop(self):
        self.pub_cmd.publish(Twist())

    def _rotate_45(self):
        twist = Twist()
        twist.angular.z = 0.5
        end_time = time.time() + (math.pi / 4) / 0.5
        while time.time() < end_time:
            self.pub_cmd.publish(twist)
            time.sleep(0.05)
        self._stop()
        time.sleep(0.2)

    def timeout_callback(self):
        self.timer.cancel()
        if self.rotation_count >= self.max_rotations:
            self.get_logger().warn("หมุนครบ 360° ไม่พบ AprilTag ข้ามไป...")
            raise SystemExit
        self.rotation_count += 1
        self.get_logger().info(
            f"ไม่พบ AprilTag หมุน 45° (ครั้งที่ {self.rotation_count}/{self.max_rotations})...")
        threading.Thread(target=self._rotate_and_restart, daemon=True).start()

    def _rotate_and_restart(self):
        self.get_logger().info("  [THREAD] เริ่มหมุน...")
        self._rotate_45()
        self.get_logger().info("  [THREAD] หมุนเสร็จ")
        if not self.found:
            self.timer = self.create_timer(self.timeout_sec, self.timeout_callback)

    def tag_callback(self, msg):
        if not msg.data:
            self.get_logger().debug("  [CB] ได้รับ msg แต่ data ว่าง")
            return
        if self.found:
            return
        self.get_logger().info(f"  [CB] ได้รับ Tag ID: {msg.data}")
        self.found = True
        self.timer.cancel()
        print(f"[AprilTag] ID: {msg.data}")
        self.get_logger().info(f"อ่านได้ AprilTag ID: {msg.data}")
        raise SystemExit


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cam_proc = subprocess.Popen(
        ['python3', os.path.join(script_dir, 'Cam_Pose_AprilTag.py')],
        preexec_fn=os.setsid
    )
    time.sleep(4.0)

    rclpy.init()
    node = AprilTagScanner()
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        try:
            os.killpg(os.getpgid(cam_proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass


if __name__ == '__main__':
    main()

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String
from geometry_msgs.msg import Twist
from yahboomcar_msgs.msg import PointArray
import time

ROTATE_SPEED = 0.3  # rad/s — ช้าพอให้กล้องจับ frame ทัน (~17°/s)
WARMUP_SEC   = 2.5  # รอกล้องเก็บ frame ก่อนเริ่มหมุน กันหมุนหนีเป้าที่อยู่ตรงหน้าแล้ว

class MissionScanner(Node):
    """ หลังถึง waypoint: รอ warmup ให้กล้องสแกนก่อน → ถ้าไม่เจอค่อยหมุนต่อเนื่องช้าๆ
        ใครเจอก่อนชนะ — เจอคน → servo drop / เจอ tag → print id
    """
    def __init__(self):
        super().__init__('mission_scanner')

        self.pub_cmd   = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_servo = self.create_publisher(Int32, '/servo_s1', 10)

        self.sub_pose = self.create_subscription(
            PointArray, '/mediapipe/points', self.pose_callback, 10)
        self.sub_tag  = self.create_subscription(
            String, '/vision/latest_at_id', self.tag_callback, 10)

        self.found = False
        self.spin_timer = None

        self.spin_twist = Twist()
        self.spin_twist.angular.z = ROTATE_SPEED

        # warmup one-shot — fire ครั้งเดียวแล้ว cancel ตัวเองใน callback
        self.warmup_timer = self.create_timer(WARMUP_SEC, self._start_spinning)
        self.get_logger().info(
            f"เริ่มสแกน — warmup {WARMUP_SEC}s ก่อนหมุน...")

    def _start_spinning(self):
        self.warmup_timer.cancel()
        if self.found:
            return
        self.spin_timer = self.create_timer(0.1, self._publish_spin)
        self.get_logger().info(
            f"warmup เสร็จ ไม่เจอเป้า → หมุน {ROTATE_SPEED} rad/s")

    def _publish_spin(self):
        if not self.found:
            self.pub_cmd.publish(self.spin_twist)

    def _stop_wheels(self):
        if self.spin_timer is not None:
            self.spin_timer.cancel()
        zero = Twist()
        for _ in range(5):
            self.pub_cmd.publish(zero)
            time.sleep(0.05)

    def pose_callback(self, msg):
        if self.found or len(msg.points) == 0:
            return
        self.found = True
        self.get_logger().info(f"เจอคน ({len(msg.points)} landmarks) → servo drop")
        self._stop_wheels()

        val = Int32()
        val.data = -90
        self.pub_servo.publish(val)
        time.sleep(1.0)
        val.data = 0
        self.pub_servo.publish(val)
        time.sleep(1.0)

        self.get_logger().info("servo เสร็จ ปิดโปรแกรม...")
        raise SystemExit

    def tag_callback(self, msg):
        if self.found or not msg.data:
            return
        self.found = True
        self._stop_wheels()
        print(f"[AprilTag] ID: {msg.data}")
        self.get_logger().info(f"เจอ AprilTag ID: {msg.data} ปิดโปรแกรม...")
        raise SystemExit


def main():
    rclpy.init()
    node = MissionScanner()
    try:
        rclpy.spin(node)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        # กันล้อค้างหมุน ตาม feedback_kill_robot_safely
        zero = Twist()
        for _ in range(5):
            node.pub_cmd.publish(zero)
            time.sleep(0.05)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

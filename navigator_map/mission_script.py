import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String
from geometry_msgs.msg import Twist
from yahboomcar_msgs.msg import PointArray
from collections import Counter
import sys
import time

ROTATE_SPEED = 0.15  # rad/s — ช้าพอให้กล้องจับ frame ทัน (~8.6°/s)
WARMUP_SEC   = 2.5   # หน้าต่างยืนนิ่งสแกน "หลังท่อ ROS ต่อติดแล้ว" ก่อนเริ่มหมุน
LINK_TIMEOUT_SEC = 8.0  # เพดานรอ DDS discovery — ถ้าเกินนี้เริ่มสแกนเลย กันค้าง
WARMUP_VOTE_MIN = 5   # เฟรม AprilTag ขั้นต่ำในหน้าต่าง warmup ถึงจะเชื่อผลโหวต
SPIN_VOTE_MIN   = 10  # เฟรม AprilTag ขั้นต่ำตอนหมุน ถึงจะหยุดแล้วโหวต
SERVO_HOLD_SEC  = 1.0 # เวลาค้างมุม servo แต่ละท่า (เตะลง / คืนตำแหน่ง)
SERVO_LINK_SEC  = 3.0 # เพดานรอ node servo จับคู่ publisher ก่อนสั่งเตะ

class MissionScanner(Node):
    """ หลังถึง waypoint: รับ type (person/tag) จาก argv → เปิด detector ตัวเดียว
        person → ยืนนิ่งสแกน เจอคน servo drop
        tag    → ยืนนิ่งเก็บเฟรม จบ warmup โหวต ID เสียงข้างมาก
        ไม่เจอในหน้าต่าง warmup → หมุนต่อเนื่องช้าๆ หาต่อ
    """
    def __init__(self, mode):
        super().__init__('mission_scanner')
        self.mode = mode  # 'person' หรือ 'tag' — มาจาก navigator_script ตาม YAML

        self.pub_cmd   = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_servo = self.create_publisher(Int32, '/servo_s1', 10)

        # เปิด subscription แค่ detector ที่ตรงกับ type ของ waypoint นี้
        # กันไม่ให้ person detector ไป servo drop ใส่คนเดินผ่านที่ tag waypoint
        if mode == 'person':
            self.sub_pose = self.create_subscription(
                PointArray, '/mediapipe/points', self.pose_callback, 10)
        else:  # 'tag'
            self.sub_tag = self.create_subscription(
                String, '/vision/latest_at_id', self.tag_callback, 10)

        self.found = False
        self.spin_timer = None
        self.tag_votes = []  # เก็บ ID ทุกเฟรมที่เห็น tag → จบ warmup ค่อยโหวตเสียงข้างมาก

        self.spin_twist = Twist()
        self.spin_twist.angular.z = ROTATE_SPEED

        # node นี้เพิ่งเกิดใหม่ (subprocess) — sub ยังไม่ match กับ publisher ของกล้อง
        # DDS discovery กินเวลา ~1-3s ถ้านับ warmup เลยตอนนี้ ข้อมูลที่กล้องส่งมา
        # ช่วงท่อยังไม่ติดจะหล่นทิ้งหมด → poll จนกล้อง match ครบ ค่อยเริ่มนับ warmup
        self.warmup_timer = None
        self._link_topic = ('/mediapipe/points' if mode == 'person'
                            else '/vision/latest_at_id')
        self._link_deadline = time.time() + LINK_TIMEOUT_SEC
        self.link_timer = self.create_timer(0.1, self._check_link)
        self.get_logger().info(f"รอท่อ ROS ({self._link_topic}) ต่อติด...")

    def _check_link(self):
        """ poll จนกล้อง publish topic ของ detector ที่ใช้ ถูก discover ค่อยเปิดสแกน """
        link_up = self.count_publishers(self._link_topic) > 0
        timed_out = time.time() >= self._link_deadline

        if not link_up and not timed_out:
            return

        self.link_timer.cancel()
        if link_up:
            self.get_logger().info(
                f"ท่อ ROS ต่อติดแล้ว → ยืนนิ่งสแกน {WARMUP_SEC}s")
        else:
            self.get_logger().warn(
                f"รอท่อ ROS เกิน {LINK_TIMEOUT_SEC}s ({self._link_topic}) "
                f"→ เริ่มสแกนเลย")

        # ตอนนี้ท่อต่อติดแล้ว — หน้าต่าง warmup นี้เป็นเวลา detect จริงทั้งก้อน
        self.warmup_timer = self.create_timer(WARMUP_SEC, self._warmup_done)

    def _warmup_done(self):
        """ จบหน้าต่างยืนนิ่งสแกน — โหวต tag ได้พอ → ตัดสิน, ไม่งั้นหมุนหาต่อ """
        self.warmup_timer.cancel()
        if self.found:
            return
        if len(self.tag_votes) >= WARMUP_VOTE_MIN:
            self._decide_tag()
            return
        self.spin_timer = self.create_timer(0.1, self._publish_spin)
        self.get_logger().info(
            f"สแกนนิ่งไม่เจอเป้า → หมุน {ROTATE_SPEED} rad/s")

    def _decide_tag(self):
        """ โหวต ID ที่เห็นบ่อยสุดจากทุกเฟรมที่เก็บมา — กันเฟรมเบลอ/อ่านพลาด """
        if self.found:
            return
        self.found = True
        self._stop_wheels()
        tag_id, votes = Counter(self.tag_votes).most_common(1)[0]
        print(f"[AprilTag] ID: {tag_id}")
        self.get_logger().info(
            f"เจอ AprilTag ID: {tag_id} (โหวต {votes}/{len(self.tag_votes)} เฟรม) ปิดโปรแกรม...")
        raise SystemExit

    def _publish_spin(self):
        if self.found:
            return
        if len(self.tag_votes) >= SPIN_VOTE_MIN:
            self._decide_tag()
            return
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
        self._drop_servo()
        self.get_logger().info("servo เสร็จ ปิดโปรแกรม...")
        raise SystemExit

    def _drop_servo(self):
        """ สั่ง servo เตะ — รอ subscriber + ส่งซ้ำ กัน DDS discovery race / QoS drop
        เดิม publish ครั้งเดียว: ถ้า node servo ยัง discover ไม่ทัน คำสั่งหาย = ไม่เตะ
        """
        deadline = time.time() + SERVO_LINK_SEC
        while self.pub_servo.get_subscription_count() == 0 and time.time() < deadline:
            time.sleep(0.05)
        if self.pub_servo.get_subscription_count() == 0:
            self.get_logger().warn("servo ยังไม่มี subscriber — ส่งคำสั่งแบบเสี่ยง")

        # กลไกเป็น dispenser ปล่อยกล่อง 1 ใบต่อ 1 strike (รอบสวิงลง -89)
        # ตั้งใจฟาด 2 ครั้ง = ปล่อย 2 กล่องต่อ waypoint เป็น safety margin
        # เผื่อกล่องใบแรกตกพลาดจุด ใบที่ 2 ตามไปเพิ่มโอกาส
        # เผื่อ margin 1° กัน mechanical stop ของ MG90S (limit ±90° เฟืองโลหะแตกง่ายถ้าชน stop)
        # 178° swing (-89↔+89) ใช้ 0.4s — MG90S no-load ใช้ 0.3s แต่ติดโหลด+DDS+S-curve เผื่อ
        # 89° swing (0→+89, -89→0) ใช้ 0.3s พอ
        self._hold_servo(+89, 0.3)   # pre-load (0 → +89 = 89°)
        self._hold_servo(-89, 0.4)   # strike 1 (178°) — ปล่อยกล่องใบ 1
        self._hold_servo(+89, 0.4)   # ยกกลับ (178°)
        self._hold_servo(-89, 0.4)   # strike 2 (178°) — ปล่อยกล่องใบ 2
        self._hold_servo(0,   0.3)   # คืนตำแหน่ง (89°)

    def _hold_servo(self, angle, duration):
        """ publish มุม servo ซ้ำทุก 0.1s ตลอด duration — คำสั่งแรกหายก็มีตัวถัดไปตาม """
        val = Int32()
        val.data = angle
        deadline = time.time() + duration
        while time.time() < deadline:
            self.pub_servo.publish(val)
            time.sleep(0.1)

    def tag_callback(self, msg):
        # เก็บทุกเฟรม ไม่ตัดสินทันที — _warmup_done / _publish_spin จะโหวตให้
        if self.found or not msg.data:
            return
        self.tag_votes.append(msg.data)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode not in ('person', 'tag'):
        print(f"[mission] ต้องระบุ type: python3 mission_script.py person|tag "
              f"(ได้รับ {mode!r})")
        sys.exit(1)
    rclpy.init()
    node = MissionScanner(mode)
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

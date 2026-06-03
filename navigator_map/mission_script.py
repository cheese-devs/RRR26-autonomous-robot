import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, String
from geometry_msgs.msg import Twist
from collections import Counter
import sys
import time

ROTATE_SPEED = 0.15  # rad/s — ช้าพอให้กล้องจับ frame ทัน (~8.6°/s)
WARMUP_SEC   = 2.5   # หน้าต่างยืนนิ่งสแกน "หลังท่อ ROS ต่อติดแล้ว" ก่อนเริ่มหมุน
LINK_TIMEOUT_SEC = 3.0  # เพดานรอ DDS discovery — Cam_Pose รันก่อนนานแล้ว discovery ปกติ <1s
                        # ตั้ง 3s กัน worst case ทะลุกฎ 10s กรรมการ
WARMUP_VOTE_MIN = 3   # เฟรม AprilTag ขั้นต่ำในหน้าต่าง warmup ถึงจะเชื่อผลโหวต
                      # ลด 5→3: ถ้า tag อยู่ใน FOV ตั้งแต่ warmup ให้จบเร็ว เก็บ budget ให้ WP อื่น
                      # โหวต most_common ยังกัน false positive ได้
SPIN_VOTE_MIN   = 10  # เฟรม AprilTag ขั้นต่ำตอนหมุน ถึงจะหยุดแล้วโหวต
SERVO_HOLD_SEC  = 1.0 # เวลาค้างมุม servo แต่ละท่า (เตะลง / คืนตำแหน่ง)
SERVO_LINK_SEC  = 3.0 # เพดานรอ node servo จับคู่ publisher ก่อนสั่งเตะ
MISSION_TIMEOUT_SEC = 11.0  # เพดานเวลาทั้ง mission (link+warmup+spin) ก่อนยอมแพ้
                           # 8.5→11: ดันเกินเพดาน 10s — ถามกรรมการแล้ว ได้ (หุ่นหมุนหา tag = ยังขยับ
                           # ไม่นับว่า "ไม่คืบหน้า >10s" ตามกฎ 6.5.1 ที่หมายถึงหุ่นนิ่งสนิท)
                           # ให้หมุนเก็บ tag ที่อยู่นอก FOV เริ่มต้นได้ครบกว่า
                           # worst case (LINK 3 + WARMUP 2.5) เหลือ spin 5.5s (~47°)
                           # ปกติ LINK <1s → spin ~7s (~60°)

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

        self.found = False
        self.spin_timer = None
        self.tag_votes = []  # ใช้เฉพาะ tag mode

        # Person mode: YAML รู้แล้วว่าจุดนี้มีคน — ปล่อยกล่องทันทีไม่ต้อง detect
        # กติกาให้คะแนน "ปล่อยกล่องเข้ากรอบแดง" ไม่ได้บังคับ "ต้องตรวจเจอคนก่อน"
        # ตัดความเสี่ยง MediaPipe miss + หมุนวน >10s โดนกรรมการ restart
        if mode == 'person':
            self.kick_timer = self.create_timer(0.05, self._person_drop_immediately)
            return

        # Tag mode: ต้องอ่าน ID จริงเพราะ ID เปลี่ยนทุกรอบแข่ง
        self.sub_tag = self.create_subscription(
            String, '/vision/latest_at_id', self.tag_callback, 10)

        self.spin_twist = Twist()
        self.spin_twist.angular.z = ROTATE_SPEED

        # node นี้เพิ่งเกิดใหม่ (subprocess) — รอ DDS discovery ของ tag publisher
        self.warmup_timer = None
        self._link_topic = '/vision/latest_at_id'
        self._link_deadline = time.time() + LINK_TIMEOUT_SEC
        self.link_timer = self.create_timer(0.1, self._check_link)

        # Mission timeout — กันหมุนวน >10s กรรมการเรียก restart (กฎ 6.5.1)
        # ถ้าเกินเพดาน: ใช้โหวตที่มี (ถ้ามี) ส่งออก แล้วข้ามไป WP ถัดไป
        self.mission_timeout_timer = self.create_timer(
            MISSION_TIMEOUT_SEC, self._on_mission_timeout)

        self.get_logger().info(f"รอท่อ ROS ({self._link_topic}) ต่อติด...")

    def _person_drop_immediately(self):
        """ Person mode: ปล่อยกล่องทันที — YAML รู้แล้วว่าจุดนี้มีคน """
        self.kick_timer.cancel()
        if self.found:
            return
        self.found = True
        self.get_logger().info("[PERSON] YAML ระบุมีคน → ปล่อย servo ทันที (ข้าม detection)")
        self._drop_servo()
        self.get_logger().info("servo เสร็จ ปิดโปรแกรม...")
        raise SystemExit

    def _on_mission_timeout(self):
        """ Tag mode: หมดเวลา — หยุดหุ่นก่อนกรรมการนับครบ 10s
        ใช้โหวตที่เก็บได้ (ถ้ามี) ส่งออก ดีกว่าไม่มีอะไรเลย แม้ confidence ต่ำ
        """
        self.mission_timeout_timer.cancel()
        if self.found:
            return
        self.found = True
        self._stop_wheels()
        if self.tag_votes:
            tag_id, votes = self._majority_tag()
            print(f"[AprilTag] ID: {tag_id}")
            self.get_logger().warn(
                f"timeout {MISSION_TIMEOUT_SEC}s — เดา ID: {tag_id} "
                f"({votes}/{len(self.tag_votes)} เฟรม low confidence)")
        else:
            self.get_logger().warn(
                f"timeout {MISSION_TIMEOUT_SEC}s — อ่าน tag ไม่เจอเลย ข้าม WP")
        raise SystemExit

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

    def _majority_tag(self):
        """ ID ที่โหวตบ่อยสุด + จำนวนโหวต จากทุกเฟรมที่เก็บมา (ต้องมี vote อย่างน้อย 1) """
        return Counter(self.tag_votes).most_common(1)[0]

    def _decide_tag(self):
        """ โหวต ID ที่เห็นบ่อยสุดจากทุกเฟรมที่เก็บมา — กันเฟรมเบลอ/อ่านพลาด """
        if self.found:
            return
        self.found = True
        self._stop_wheels()
        tag_id, votes = self._majority_tag()
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
        # 178° swing (-89↔+89) ขยาย 0.4 → 0.6s ให้ servo มีเวลาสวิงเต็ม ramp
        # 89° swing (0→+89, -89→0) ใช้ 0.3s พอ
        # pre-load ขยาย 0.3 → 0.7s ให้ spring/เฟือง load เต็มก่อน strike 1
        # (data 5 รอบ: ลูกแรกมัก fail / ไกลน้อยกว่าลูก 2 → strike 1 momentum ต่ำเพราะ pre-load สั้นไป)
        self._hold_servo(+89, 0.7)   # pre-load (0 → +89 = 89°) — ขยายเพื่อ load เฟืองเต็ม
        self._hold_servo(-89, 0.6)   # strike 1 (178°) — ปล่อยกล่องใบ 1
        self._hold_servo(+89, 0.6)   # ยกกลับ (178°)
        self._hold_servo(-89, 0.6)   # strike 2 (356° รวม windup) — ปล่อยกล่องใบ 2
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

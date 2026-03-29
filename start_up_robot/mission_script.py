import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from yahboomcar_msgs.msg import PointArray
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import time

class SingleActionWithTimeout(Node):
    def __init__(self):
        super().__init__('single_action_timeout')
        
        # ปรับ QoS เป็น Reliable (มั่นใจว่าส่งถึง) และเก็บข้อมูลล่าสุดไว้ 10 ชุด
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        self.pub_servo = self.create_publisher(Int32, '/servo_s1', qos_profile)
        self.sub_points = self.create_subscription(
            PointArray,
            '/mediapipe/points',
            self.listener_callback,
            10)
        
        # สร้าง Timer ให้ทำงานหลังจากผ่านไป 5 วินาที
        self.timeout_sec = 5.0
        self.timer = self.create_timer(self.timeout_sec, self.timeout_callback)
        
        self.get_logger().info(f"เริ่มรอตรวจจับ (มีเวลา {self.timeout_sec} วินาที)... [QoS: Reliable]")

    def send_servo_command(self, angle, repeat=3):
        """ ฟังก์ชันช่วยส่งคำสั่ง Servo ซ้ำตามจำนวนที่กำหนด """
        val = Int32()
        val.data = angle
        for i in range(repeat):
            self.pub_servo.publish(val)
            # ดีเลย์สั้นๆ ระหว่างการส่งซ้ำ (เช่น 0.05 วินาที) เพื่อไม่ให้บัฟเฟอร์ล้นแต่ยังมั่นใจว่าส่งไปแน่
            time.sleep(0.05) 
        self.get_logger().info(f"ส่งคำสั่งมุม {angle} ไปยัง Servo จำนวน {repeat} ครั้งสำเร็จ")

    def timeout_callback(self):
        self.get_logger().warn("หมดเวลา 5 วินาที: ไม่พบข้อมูล ปิดโปรแกรม...")
        raise SystemExit

    def listener_callback(self, msg):
        if len(msg.points) > 0:
            # หยุด Timer ทันทีเมื่อเจอข้อมูล
            self.timer.cancel()
            self.get_logger().info("ตรวจพบข้อมูล! กำลังเริ่มทำงาน...")

            # 1. สั่งไปที่ -40 (ส่ง 3 ครั้ง)
            self.send_servo_command(-40, repeat=3)
            time.sleep(1.0) # รอให้ Servo เคลื่อนที่จริง

            # 2. สั่งกลับมาที่ 0 (ส่ง 3 ครั้ง)
            self.send_servo_command(0, repeat=3)
            time.sleep(1.0) # รอให้ Servo เคลื่อนที่จริง

            self.get_logger().info("ทำงานเสร็จสิ้น ปิดโปรแกรม...")
            raise SystemExit

def main():
    rclpy.init()
    node = SingleActionWithTimeout()
    try:
        rclpy.spin(node)
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

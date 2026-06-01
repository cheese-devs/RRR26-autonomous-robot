#!/usr/bin/env python3
import rclpy, subprocess, os
from rclpy.node import Node
from std_msgs.msg import UInt16, Int32
from rclpy.qos import QoSProfile, ReliabilityPolicy

qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

class BatteryMonitor(Node):
    def __init__(self):
        super().__init__('battery_monitor')
        self.sub = self.create_subscription(UInt16, '/battery', self.cb, qos)
        self.pub_beep = self.create_publisher(Int32, '/beep', 10)
        self.warned = False

    def cb(self, msg):
        v = msg.data / 10.0
        # หุ่นตัวนี้ IMU เริ่มเอ๋อ/หมุนเองตั้งแต่ ~7.8-7.9V (สูงกว่า cutoff ทางไฟฟ้ามาก)
        # เตือนที่ 8.0V เพื่อให้เปลี่ยนแบตทันก่อน yaw drift
        if msg.data < 80 and not self.warned:
            self.warned = True
            print(f'WARNING: แบตต่ำกว่า 8.0V! ({v}V) — IMU จะเริ่มเอ๋อ เปลี่ยนแบตด่วน', flush=True)
            display = os.environ.get('DISPLAY', ':0')
            subprocess.Popen(
                ['notify-send', '-u', 'critical', 'แบตต่ำ!', f'แบตเหลือ {v}V (ต่ำกว่า 8.0V) — IMU จะเอ๋อ', '--icon=battery-caution'],
                env={**os.environ, 'DISPLAY': display}
            )
            beep_msg = Int32()
            beep_msg.data = 1000
            for _ in range(3):
                self.pub_beep.publish(beep_msg)
        elif msg.data >= 80:
            self.warned = False

rclpy.init()
node = BatteryMonitor()
rclpy.spin(node)

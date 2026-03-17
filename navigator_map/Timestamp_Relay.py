import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

class LaserTimestampFixer(Node):
    def __init__(self):
        super().__init__('laser_timestamp_fixer')
        # รับจากหัวข้อที่ micro-ROS ส่งมา (เช่น /scan_raw)
        self.subscription = self.create_subscription(LaserScan, '/scan_raw', self.listener_callback, 10)
        # ส่งต่อไปยังหัวข้อที่ AMCL ใช้งานจริง (เช่น /scan)
        self.publisher_ = self.create_publisher(LaserScan, '/scan', 10)

    def listener_callback(self, msg):
        # ปั๊มเวลาปัจจุบันของคอมพิวเตอร์ใส่เข้าไป
        msg.header.stamp = self.get_clock().now().to_msg()
        # ส่งข้อมูลที่แก้ไขเวลาแล้วออกไป
        self.publisher_.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = LaserTimestampFixer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
if __name__ == '__main__':
    main()

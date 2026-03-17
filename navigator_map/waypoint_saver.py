import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseWithCovarianceStamped
import yaml
import sys, tty, termios

class WaypointSaver(Node):
    def __init__(self):
        super().__init__('waypoint_saver')
        self.subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            '/initialpose',
            self.listener_callback,
            10)
        self.waypoints = []
        self.temp_msg = None # เก็บค่าล่าสุดที่คลิกจาก RViz ไว้ชั่วคราว
        self.get_logger().info('--- Waypoint Saver Ready ---')
        self.get_logger().info('1. Click "2D Pose Estimate" in RViz2')
        self.get_logger().info('2. Press "s" in this terminal to SAVE that point')

    def listener_callback(self, msg):
        # เมื่อคลิกใน RViz ให้เก็บค่าไว้รอการยืนยัน
        self.temp_msg = msg
        pos = msg.pose.pose.position
        self.get_logger().info(f'Selected: x={pos.x:.3f}, y={pos.y:.3f} (Press "s" to save or click again to change)')

    def save_waypoint(self):
        if self.temp_msg is None:
            print("\n[SKIP] Please select a point in RViz first!")
            return

        pos = self.temp_msg.pose.pose.position
        ori = self.temp_msg.pose.pose.orientation
        
        current_count = len(self.waypoints) + 1
        waypoint_name = f'waypoint_{current_count}'
        
        waypoint_data = {
            'task': waypoint_name,
            'x': round(pos.x, 3),
            'y': round(pos.y, 3),
            'orientation': {
                'z': round(ori.z, 5),
                'w': round(ori.w, 5)
            }
        }
        
        self.waypoints.append(waypoint_data)
        
        with open('nav_waypoints.yaml', 'w') as f:
            yaml.dump({'waypoints': self.waypoints}, f, sort_keys=False)
        
        print(f"\n[SAVED] {waypoint_name} added to nav_waypoints.yaml")
        self.temp_msg = None # ล้างค่าชั่วคราวเพื่อรอจุดถัดไป

def get_key(settings):
    tty.setraw(sys.stdin.fileno())
    key = sys.stdin.read(1)
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key

def main(args=None):
    rclpy.init(args=args)
    node = WaypointSaver()
    settings = termios.tcgetattr(sys.stdin)

    try:
        while rclpy.ok():
            # ตรวจสอบ Topic และรัน Callback
            rclpy.spin_once(node, timeout_sec=0.1)
            
            # ดักจับการกดปุ่ม (ใช้ระบบ Non-blocking เล็กน้อยผ่าน Timeout ของ spin)
            # หมายเหตุ: ใน Linux การอ่าน stdin อาจจะรอ (Block) ถ้าไม่ได้กดปุ่ม
            # แต่ในที่นี้เราเน้นความง่ายในการใช้งาน
            key = get_key(settings).lower()
            
            if key == 's':
                node.save_waypoint()
            elif key == '\x03': # Ctrl+C
                break

    except Exception as e:
        print(f"Error: {e}")
    finally:
        print(f'\nFinished! Total {len(node.waypoints)} waypoints saved.')
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

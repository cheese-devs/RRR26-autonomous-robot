import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
from std_msgs.msg import Bool
import yaml
import time
import signal
import subprocess  # สำหรับรันสคริปต์ภายนอก

class TaskNavigator:
    def __init__(self):
        self.nav = BasicNavigator()
        self.cmd_vel_pub = self.nav.create_publisher(Twist, '/cmd_vel', 10)
        self.detect_pub = self.nav.create_publisher(Bool, '/vision/detect_enable', 10)

    def set_detect(self, enabled):
        msg = Bool(); msg.data = enabled
        # publish ซ้ำ 3 ครั้งกัน QoS drop ตอน cam ยังไม่ subscribe
        for _ in range(3):
            self.detect_pub.publish(msg)
            time.sleep(0.05)

    def emergency_stop(self):
        """ ยกเลิก nav task + ส่ง zero /cmd_vel ซ้ำๆ ให้ล้อหุ่นหยุดสนิท """
        try:
            self.nav.cancelTask()
        except Exception:
            pass
        zero = Twist()
        for _ in range(5):
            self.cmd_vel_pub.publish(zero)
            time.sleep(0.05)
        print("[STOP] sent zero /cmd_vel — robot halted")

    def run_external_script(self):
        """ ฟังก์ชันสำหรับรันสคริปต์ภายนอกและรอจนกว่าจะเสร็จ """
        script_path = "mission_script.py" # เปลี่ยนเป็นชื่อไฟล์สคริปต์ภารกิจของคุณ
        print(f"   -> กำลังเริ่มรันสคริปต์ภารกิจ: {script_path}")
        
        try:
            # รันสคริปต์และรอ (Wait) จนกว่ากระบวนการจะจบ
            process = subprocess.run(["python3", script_path], check=True)
            print("   -> ภารกิจในสคริปต์เสร็จสิ้นแล้ว")
        except subprocess.CalledProcessError as e:
            print(f"   -> [ERROR] สคริปต์ภารกิจทำงานผิดพลาด: {e}")
        except FileNotFoundError:
            print(f"   -> [ERROR] ไม่พบไฟล์สคริปต์ที่ระบุ: {script_path}")

    def perform_task(self, waypoint_name):
        """ ภารกิจที่ทำเมื่อถึงจุดหมาย """
        # ตรวจสอบว่าชื่อ waypoint ใช่ "HOME" หรือไม่ (ตัวเล็กตัวใหญ่มีผล)
        if waypoint_name.upper() == "HOME":
            print(f"--- ถึงจุด {waypoint_name}: ทำการ Reset ระบบและหยุดรอ ---")
            time.sleep(2)
        else:
            print(f"--- ถึงจุด {waypoint_name}: เริ่มรันสคริปต์ภารกิจพิเศษ ---")
            self.set_detect(True)
            time.sleep(0.5)  # ให้ cam รับ enable + เริ่ม publish /mediapipe/points
            try:
                self.run_external_script()
            finally:
                self.set_detect(False)

        print(f"--- เสร็จสิ้นภารกิจที่ {waypoint_name} ---\n")
def main():
    rclpy.init()
    task_nav = TaskNavigator()
    nav = task_nav.nav

    def _sigterm_handler(signum, _frame):
        print(f"\n[SIGNAL {signum}] หยุดหุ่นและออก...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        _run(task_nav, nav)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] หยุดหุ่น...")
    finally:
        task_nav.emergency_stop()
        if rclpy.ok():
            rclpy.shutdown()


def _run(task_nav, nav):
    print("กำลังรอให้ Nav2 พร้อมใช้งาน...")
    nav.waitUntilNav2Active()

    # เริ่ม Loop ใหญ่เพื่อให้รับค่าได้เรื่อยๆ
    while rclpy.ok():
        # โหลดไฟล์ YAML ทุกครั้งที่เริ่มรอบใหม่ (เผื่อมีการอัปเดตไฟล์ขณะโปรแกรมรัน)
        try:
            with open('nav_waypoints.yaml', 'r') as f:
                data = yaml.safe_load(f)
                all_waypoints = data['waypoints']
        except Exception as e:
            print(f"Error loading YAML: {e}")
            break

        # แสดงรายการ Waypoint
        print("\n" + "="*30)
        print("รายการ Waypoints ที่พร้อมใช้งาน:")
        for i, wp in enumerate(all_waypoints):
            print(f"[{i+1}] {wp['task']} (x: {wp['x']}, y: {wp['y']},z: {wp['orientation']['z']}, w: {wp['orientation']['w']})")
        print("[0] ออกจากโปรแกรม (Exit)")
        print("="*30)
        
        # รับค่า Input
        user_input = input("\nระบุลำดับการวิ่ง (เช่น 3,1,2) หรือกด 0 เพื่อเลิก: ")
        
        if user_input.strip() == '0':
            print("ปิดโปรแกรม...")
            break
        
        try:
            order_indices = [int(x.strip()) - 1 for x in user_input.split(',') if x.strip()]
            planned_waypoints = [all_waypoints[i] for i in order_indices]
        except (ValueError, IndexError):
            print("[!] ใส่ตัวเลขไม่ถูกต้อง กรุณาลองใหม่")
            continue

        # เริ่มการเดินทางตามลำดับที่ป้อน
        print(f"\nเริ่มการเดินทางทั้งหมด {len(planned_waypoints)} จุด...")
        
        for wp in planned_waypoints:
            goal_pose = PoseStamped()
            goal_pose.header.frame_id = 'map'
            goal_pose.header.stamp = nav.get_clock().now().to_msg()
            goal_pose.pose.position.x = wp['x']
            goal_pose.pose.position.y = wp['y']
            goal_pose.pose.orientation.z = wp['orientation']['z']
            goal_pose.pose.orientation.w = wp['orientation']['w']

            print(f">> มุ่งหน้าไป: {wp['task']}")
            nav.goToPose(goal_pose)

            # ตรวจสอบสถานะการวิ่ง
            while not nav.isTaskComplete():
                # คุณสามารถเพิ่ม logic ตรวจสอบ Feedback ตรงนี้ได้
                pass

            result = nav.getResult()
            if result == TaskResult.SUCCEEDED:
                task_nav.perform_task(wp['task'])
            elif result == TaskResult.CANCELED:
                print(f"ภารกิจไป {wp['task']} ถูกยกเลิก")
                break
            elif result == TaskResult.FAILED:
                print(f"ไม่สามารถไปถึง {wp['task']} ได้ (อาจมีสิ่งกีดขวาง)")
                break

        print("\n[SUCCESS] วิ่งครบตามแผนงานแล้ว!")
        print("กลับไปรอรับคำสั่งชุดใหม่...")


if __name__ == '__main__':
    main()


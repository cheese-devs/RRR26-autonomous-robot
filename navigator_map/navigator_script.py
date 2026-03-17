import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
import yaml
import time
import subprocess  # สำหรับรันสคริปต์ภายนอก

class TaskNavigator:
    def __init__(self):
        self.nav = BasicNavigator()
        self.cmd_vel_pub = self.nav.create_publisher(Twist, '/cmd_vel', 10)

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
            # เรียกรันสคริปต์ภายนอก
            self.run_external_script()
            
        print(f"--- เสร็จสิ้นภารกิจที่ {waypoint_name} ---\n")

def main():
    rclpy.init()
    task_nav = TaskNavigator()
    nav = task_nav.nav

    nav.waitUntilNav2Active()

    # โหลดไฟล์ YAML
    try:
        with open('nav_waypoints.yaml', 'r') as f:
            data = yaml.safe_load(f)
            all_waypoints = data['waypoints']
    except Exception as e:
        print(f"Error loading YAML: {e}")
        return

    # แสดงรายการและเลือกลำดับ
    print(f"\nพบจุดทั้งหมด {len(all_waypoints)} จุด")
    for i, wp in enumerate(all_waypoints):
        print(f"[{i+1}] {wp['task']}")
    
    order_input = input("\nระบุลำดับการวิ่ง (เช่น 3,1,2): ")
    order_indices = [int(x.strip()) - 1 for x in order_input.split(',')]
    planned_waypoints = [all_waypoints[i] for i in order_indices]

    for wp in planned_waypoints:
        goal_pose = PoseStamped()
        goal_pose.header.frame_id = 'map'
        goal_pose.header.stamp = nav.get_clock().now().to_msg()
        goal_pose.pose.position.x = wp['x']
        goal_pose.pose.position.y = wp['y']
        goal_pose.pose.orientation.z = wp['orientation']['z']
        goal_pose.pose.orientation.w = wp['orientation']['w']

        print(f"กำลังมุ่งหน้าไป: {wp['task']}")
        nav.goToPose(goal_pose)

        while not nav.isTaskComplete():
            pass

        if nav.getResult() == TaskResult.SUCCEEDED:
            # ส่งชื่อ waypoint เข้าไปเช็คใน perform_task
            task_nav.perform_task(wp['task'])
        else:
            print(f"ไม่สามารถไปถึง {wp['task']} ได้")
            break

    print("จบการทำงาน")
    rclpy.shutdown()

if __name__ == '__main__':
    main()

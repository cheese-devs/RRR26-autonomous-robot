import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
from std_msgs.msg import Bool
import yaml
import time
import signal
import subprocess  # สำหรับรันสคริปต์ภายนอก

CLEAR_SETTLE_SEC = 1.0   # หลังเคลียร์ costmap รอ scan สดมาร์ก obstacle จริงกลับเข้ามา
MAX_NAV_RETRY    = 1     # ลองซ้ำเมื่อ FAILED กี่ครั้ง (รวมแล้ววิ่งสูงสุด 2 รอบ/จุด)

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

    def run_external_script(self, wp_type):
        """ รันสคริปต์ภารกิจและรอจนเสร็จ — ส่ง type (person/tag) ให้เป็น argv """
        script_path = "mission_script.py"
        print(f"   -> กำลังเริ่มรันสคริปต์ภารกิจ: {script_path} (type={wp_type})")
        
        try:
            # รันสคริปต์และรอ (Wait) จนกว่ากระบวนการจะจบ
            subprocess.run(["python3", "-u", script_path, wp_type], check=True)
            print("   -> ภารกิจในสคริปต์เสร็จสิ้นแล้ว")
        except subprocess.CalledProcessError as e:
            print(f"   -> [ERROR] สคริปต์ภารกิจทำงานผิดพลาด: {e}")
        except FileNotFoundError:
            print(f"   -> [ERROR] ไม่พบไฟล์สคริปต์ที่ระบุ: {script_path}")

    def perform_task(self, wp):
        """ ภารกิจที่ทำเมื่อถึงจุดหมาย — wp คือ dict ทั้งก้อนจาก YAML """
        waypoint_name = wp['task']
        # ตรวจสอบว่าชื่อ waypoint ใช่ "HOME" หรือไม่ (ตัวเล็กตัวใหญ่มีผล)
        if waypoint_name.upper() == "HOME":
            print(f"--- ถึงจุด {waypoint_name}: ทำการ Reset ระบบและหยุดรอ ---")
            time.sleep(2)
        else:
            wp_type = wp.get('type')
            if wp_type not in ('person', 'tag'):
                # ไม่มี type = ไม่รู้จะเปิด detector ตัวไหน — ข้ามดีกว่าเสี่ยงทำผิด
                print(f"--- [!] {waypoint_name}: YAML ไม่ได้ระบุ type "
                      f"(person/tag) → ข้ามภารกิจ ---")
            else:
                print(f"--- ถึงจุด {waypoint_name}: เริ่มภารกิจ (type={wp_type}) ---")
                self.set_detect(True)
                time.sleep(0.5)  # ให้ cam รับ enable + เริ่ม publish topic
                try:
                    self.run_external_script(wp_type)
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


def _goto_pose(nav, goal_pose, name):
    """ ไป waypoint โดยเคลียร์ 'ผี' ใน costmap ก่อนทุกครั้ง + ลองซ้ำเมื่อ FAILED

    clearAllCostmaps() รีเซ็ต obstacle_layer กลับเป็น static map — obstacle ของจริง
    จะถูก scan สดมาร์กกลับเข้ามาใน ~1s แต่มาร์กค้าง/ดริฟต์จาก mislocalization หายไป
    """
    result = None
    for attempt in range(MAX_NAV_RETRY + 1):
        try:
            nav.clearAllCostmaps()
        except Exception as e:
            print(f"   [!] เคลียร์ costmap ไม่สำเร็จ: {e}")
        time.sleep(CLEAR_SETTLE_SEC)

        if attempt == 0:
            print(f">> มุ่งหน้าไป: {name}")
        else:
            print(f">> ลองซ้ำ {name} (รอบ {attempt + 1}) — เคลียร์ผีแล้วลองใหม่")

        goal_pose.header.stamp = nav.get_clock().now().to_msg()
        nav.goToPose(goal_pose)
        while not nav.isTaskComplete():
            pass

        result = nav.getResult()
        if result == TaskResult.SUCCEEDED:
            return result
        if result == TaskResult.CANCELED:
            return result  # ถูกยกเลิก (Ctrl+C/SIGTERM) — ไม่ลองซ้ำ
        print(f"   [!] {name} FAILED (รอบ {attempt + 1})")
    return result


def _make_pose(nav, p):
    """ แปลง dict {x, y, orientation:{z,w}} เป็น PoseStamped บน frame map """
    gp = PoseStamped()
    gp.header.frame_id = 'map'
    gp.header.stamp = nav.get_clock().now().to_msg()
    gp.pose.position.x = p['x']
    gp.pose.position.y = p['y']
    gp.pose.orientation.z = p['orientation']['z']
    gp.pose.orientation.w = p['orientation']['w']
    return gp


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
        
        all_done = True  # False ถ้ามี waypoint ถูกยกเลิก/ไปไม่ถึง
        for wp in planned_waypoints:
            # จุดคั่น (via) ถ้ามี — วิ่งผ่านก่อนโดยไม่สแกนภารกิจ
            ok = True
            for vp in wp.get('via', []):
                vname = f"จุดคั่นก่อน {wp['task']} ({vp['x']}, {vp['y']})"
                result = _goto_pose(nav, _make_pose(nav, vp), vname)
                if result != TaskResult.SUCCEEDED:
                    ok = False
                    break
            if not ok:
                if result == TaskResult.CANCELED:
                    print(f"ภารกิจไป {wp['task']} ถูกยกเลิก")
                else:
                    print(f"ไปจุดคั่นก่อน {wp['task']} ไม่ได้ — ลองซ้ำครบแล้ว")
                all_done = False
                break

            result = _goto_pose(nav, _make_pose(nav, wp), wp['task'])
            if result == TaskResult.SUCCEEDED:
                task_nav.perform_task(wp)
            elif result == TaskResult.CANCELED:
                print(f"ภารกิจไป {wp['task']} ถูกยกเลิก")
                all_done = False
                break
            else:  # FAILED (หรือ None) — ลองซ้ำครบโควต้าแล้วยังไม่ถึง
                print(f"ไม่สามารถไปถึง {wp['task']} ได้ (อาจมีสิ่งกีดขวาง) — ลองซ้ำครบแล้ว")
                all_done = False
                break

        if all_done:
            print("\n[SUCCESS] วิ่งครบตามแผนงานแล้ว!")
        else:
            print("\n[ABORT] แผนงานหยุดกลางคัน — มี waypoint ที่ไปไม่ถึง")
        print("กลับไปรอรับคำสั่งชุดใหม่...")


if __name__ == '__main__':
    main()


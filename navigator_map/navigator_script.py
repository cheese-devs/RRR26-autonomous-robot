"""
ตัวขับ waypoint mission อัตโนมัติ — process หลักของ Phase 3 (วันแข่ง)

หน้าที่:
    - อ่าน waypoint จาก nav_waypoints.yaml + รับลำดับที่จะวิ่งจาก stdin (interactive)
    - ขับหุ่นไปทีละ waypoint ผ่าน Nav2 (clearCostmap → goToPose) พร้อม watchdog
      "ไม่คืบหน้า >timeout" และ retry เมื่อ FAILED
    - ที่ waypoint ที่ไม่ใช่ HOME → spawn `mission_script.py <type>` เป็น subprocess
      (person = ปล่อยกล่อง, tag = อ่าน AprilTag)
    - exit_pocket(): ถอยออกจากซอก U ของ survivor zone ด้วย Nav2 BackUp (collision-aware)
      กัน DWB ค้างตอนไป waypoint ถัดไป
    - emergency_stop(): cancel task + ปล่อย zero /cmd_vel ×5 ก่อนจบ (กันล้อหมุนค้าง)

วิธีรัน:
    cd navigator_map
    python3 navigator_script.py            # แล้วพิมพ์ลำดับ เช่น 1,2,3,4,5,6 จากนั้น 0 เพื่อจบ
    printf '1,2,3,4,5,6\\n0\\n' | python3 navigator_script.py   # non-interactive

หมายเหตุ: ต้องเป็น CWD = navigator_map/ (path สัมพัทธ์), Nav2 ต้อง active ก่อน
"""
import rclpy
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from geometry_msgs.msg import PoseStamped, Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import Bool
import yaml
import time
import signal
import subprocess  # สำหรับรันสคริปต์ภายนอก

CLEAR_SETTLE_SEC = 1.0   # หลังเคลียร์ costmap รอ scan สดมาร์ก obstacle จริงกลับเข้ามา
MAX_NAV_RETRY    = 1     # ลองซ้ำเมื่อ FAILED กี่ครั้ง (รวมแล้ววิ่งสูงสุด 2 รอบ/จุด)

# หลัง mission (person/tag) หุ่นหมุนหาเป้า → อาจค้างในซอก U ของ survivor zone:
# ตัวหุ่นยืนคร่อม inflated cells หลายด้านพร้อมกัน → DWB หา trajectory ไม่ได้ ออก 0 m/s
# วิธีกัน: ถอยออกจากซอกด้วย Nav2 BackUp behavior (collision-aware) ก่อนสั่ง goToPose จุดถัดไป
# 0.20m พอตรงทฤษฎี แต่จริงไม่พ้นซอก U → 0.30m พอออกแต่ไม่ชนกำแพงหลัง (หลังขยับ WP เข้า 5cm)
# เคยใช้ 0.50m แต่ชนกำแพงด้านหลังของซอกหลังขยับ WP1/WP4 เข้า 5cm → BackUp FAILED → ติดในซอก
# speed 0.05→0.12: ที่ 0.05 ถอย 0.60m ต้องใช้ 12s แต่ติด time_allowance 8s → ถอยได้แค่ ~0.40m
# (ไม่พ้นซอกจริงตามที่ตั้งใจ) ที่ 0.12 ถอยครบ 0.60m ใน 5s — เร็วขึ้น + ถอยครบ collision-aware กันชน
POCKET_BACKUP_DIST_M       = 0.60
POCKET_BACKUP_SPEED_MPS    = 0.12
POCKET_BACKUP_TIMEOUT_SEC  = 8

# Retry recovery: attempt 1 อาจพาหุ่นเข้าซอกแคบจน DWB ค้าง — ถอยสั้นๆ ก่อน plan ใหม่
# 0.30m พอดึงออกจากจุดติดโดยไม่ไปไกลจน plan ใหม่อ้อมเยอะ
RETRY_BACKUP_DIST_M       = 0.30
RETRY_BACKUP_TIMEOUT_SEC  = 5

# Watchdog: กฎกรรมการ 6.5.1.2 — ไม่คืบหน้า >10s ถูกบังคับ retry (เสียซูเปอร์บิงโก)
# ตั้ง 8s เพื่อให้เหลือ buffer ~2s สำหรับ cancel + clearCostmap + เริ่ม attempt ใหม่
# ก่อนกรรมการจะนับครบ 10s
NO_PROGRESS_TIMEOUT_SEC = 8.0
# "ขยับ" = velocity ใน odom เกินค่านี้ (เชิงเส้น m/s หรือเชิงมุม rad/s)
# หุ่นถอย/หมุนช้าใน recovery ก็ยังถือว่าไม่ stuck — กฎกรรมการคือ "ไม่คืบหน้า" = ไม่ขยับ
ODOM_LIN_EPSILON_MPS    = 0.01   # 1 cm/s
ODOM_ANG_EPSILON_RPS    = 0.05   # ~3 deg/s
HARD_TIMEOUT_SEC        = 120.0  # ต่อ 1 attempt — กันกรณี feedback ค้าง/edge case
FEEDBACK_POLL_SEC       = 0.2
# ใกล้ goal เท่านี้ → skip watchdog (Nav2 หมุนเข้า yaw — distance_remaining จะนิ่ง)
# ต้อง ≥ xy_goal_tolerance(0.15) + เผื่อจิตเตอร์
GOAL_APPROACH_DIST_M    = 0.25

class TaskNavigator:
    def __init__(self):
        self.nav = BasicNavigator()
        self.cmd_vel_pub = self.nav.create_publisher(Twist, '/cmd_vel', 10)
        self.detect_pub = self.nav.create_publisher(Bool, '/vision/detect_enable', 10)
        # Odom velocity สำหรับ watchdog — กฎกรรมการคือ "หุ่นไม่ขยับ"
        # ใช้ velocity ตรงๆ ครอบคลุมทั้งเดินหน้า/ถอย/หมุน (recovery behavior)
        self.last_odom_vel = None  # (linear_speed, angular_speed)
        self.nav.create_subscription(Odometry, '/odom', self._odom_cb, 10)

    def _odom_cb(self, msg):
        lin = msg.twist.twist.linear
        ang = msg.twist.twist.angular
        lin_speed = (lin.x * lin.x + lin.y * lin.y) ** 0.5
        self.last_odom_vel = (lin_speed, abs(ang.z))

    def set_detect(self, enabled):
        msg = Bool(); msg.data = enabled
        # publish ซ้ำ 3 ครั้งกัน QoS drop ตอน cam ยังไม่ subscribe
        for _ in range(3):
            self.detect_pub.publish(msg)
            time.sleep(0.05)

    def exit_pocket(self):
        """ ถอยออกจากซอก U หลัง mission — กัน DWB ค้างในจุดถัดไป

        ใช้ Nav2 BackUp behavior (collision-aware ผ่าน behavior_server) — ถ้าด้านหลัง
        มีกำแพง simulate_ahead_time=2.0s จะปฏิเสธ คืน FAILED แล้วเราเดินหน้าต่อไม่ crash

        ตอน mission_script รัน (warmup 2.5s + spin หา tag + servo) local costmap สะสม
        ghost obstacles (AMCL drift / sensor noise) → BackUp collision check refuse
        เคลียร์ก่อนเรียก backup → ลด false positive (กำแพงจริงห่าง 60cm แต่ ghost ใกล้กว่า)
        """
        nav = self.nav
        try:
            nav.clearAllCostmaps()
            time.sleep(CLEAR_SETTLE_SEC)
            accepted = nav.backup(
                backup_dist=POCKET_BACKUP_DIST_M,
                backup_speed=POCKET_BACKUP_SPEED_MPS,
                time_allowance=POCKET_BACKUP_TIMEOUT_SEC,
            )
            if accepted is False:
                print("   [!] BackUp ถูกปฏิเสธ — ข้าม")
                return
            print(f"   ถอยออกจากซอก {POCKET_BACKUP_DIST_M:.2f}m ก่อนไปจุดถัดไป...")
            while not nav.isTaskComplete():
                time.sleep(0.1)
            result = nav.getResult()
            if result != TaskResult.SUCCEEDED:
                print(f"   [!] BackUp ไม่สำเร็จ ({result}) — เดินหน้าต่อ")
        except Exception as e:
            print(f"   [!] BackUp error: {e} — เดินหน้าต่อ")

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
        """ รันสคริปต์ภารกิจและรอจนเสร็จ — ส่ง type (person/tag) ให้เป็น argv

        timeout=12s ครอบ worst case ของลูก:
          startup ~2s + MISSION_TIMEOUT_SEC 8.5s + cleanup ~1s = ~11.5s + buffer
        เกิน timeout → subprocess ส่ง SIGKILL ฆ่าลูก พ่อหลุดไป WP ถัดไป
        ถ้าไม่มี timeout: ลูกค้างก่อน timer ในตัวสร้าง (rclpy.init / DDS) → block ตลอดไป
        → หุ่นนิ่ง >10s กรรมการสั่ง retry เสียซูเปอร์บิงโก
        """
        script_path = "mission_script.py"
        print(f"   -> กำลังเริ่มรันสคริปต์ภารกิจ: {script_path} (type={wp_type})")

        try:
            subprocess.run(
                ["python3", "-u", script_path, wp_type],
                check=True,
                timeout=12.0,
            )
            print("   -> ภารกิจในสคริปต์เสร็จสิ้นแล้ว")
        except subprocess.TimeoutExpired:
            print(f"   -> [TIMEOUT] mission_script ค้าง >12s — ฆ่าทิ้ง ข้าม WP ไปต่อ")
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
            time.sleep(0.5)  # กลับถึงบ้านแล้วไม่ต้องรอนาน — ประหยัดเวลา 5 นาที
        else:
            wp_type = wp.get('type')
            if wp_type not in ('person', 'tag'):
                # ไม่มี type = ไม่รู้จะเปิด detector ตัวไหน — ข้ามดีกว่าเสี่ยงทำผิด
                print(f"--- [!] {waypoint_name}: YAML ไม่ได้ระบุ type "
                      f"(person/tag) → ข้ามภารกิจ ---")
            else:
                print(f"--- ถึงจุด {waypoint_name}: เริ่มภารกิจ (type={wp_type}) ---")
                # person mode ปล่อย servo ทันทีโดยไม่ดูกล้อง → ไม่ต้องเปิด detect
                # เปิด AprilTag เฉพาะ tag waypoint (vision node ไม่มี detector อื่นแล้ว)
                use_detect = (wp_type == 'tag')
                if use_detect:
                    self.set_detect(True)
                    time.sleep(0.5)  # ให้ cam รับ enable + เริ่ม publish topic
                try:
                    self.run_external_script(wp_type)
                finally:
                    if use_detect:
                        self.set_detect(False)
                # ถอยออกจากซอกเฉพาะ person — wp person อยู่ในซอก U survivor zone
                # (กำแพง 3 ด้าน) หุ่นปล่อยกล่องแล้วต้องถอยก่อน plan จุดถัดไป ไม่งั้น DWB ค้าง
                # tag อยู่ที่โล่งกว่า planner เดินออกได้เลย → ข้าม BackUp ประหยัด ~5s/จุด
                if wp_type == 'person':
                    self.exit_pocket()

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


def _goto_pose(task_nav, goal_pose, name):
    """ ไป waypoint โดยเคลียร์ 'ผี' ใน costmap ก่อนทุกครั้ง + ลองซ้ำเมื่อ FAILED

    clearAllCostmaps() รีเซ็ต obstacle_layer กลับเป็น static map — obstacle ของจริง
    จะถูก scan สดมาร์กกลับเข้ามาใน ~1s แต่มาร์กค้าง/ดริฟต์จาก mislocalization หายไป
    """
    nav = task_nav.nav
    result = None
    for attempt in range(MAX_NAV_RETRY + 1):
        # ก่อน retry: ถอยสั้นๆ ด้วย Nav2 BackUp (collision-aware) — ถ้า attempt ก่อนหน้า
        # พาหุ่นเข้าซอกแคบจน DWB หา trajectory ไม่ได้ ดึงออกก่อน plan ใหม่
        # ด้านหลังมีกำแพง → BackUp จะ refuse คืน FAILED → fall-through ไป clearCostmaps ต่อ
        if attempt > 0:
            try:
                accepted = nav.backup(
                    backup_dist=RETRY_BACKUP_DIST_M,
                    backup_speed=POCKET_BACKUP_SPEED_MPS,
                    time_allowance=RETRY_BACKUP_TIMEOUT_SEC,
                )
                if accepted is not False:
                    print(f"   ถอย {RETRY_BACKUP_DIST_M:.2f}m ก่อน retry...")
                    while not nav.isTaskComplete():
                        time.sleep(0.1)
            except Exception as e:
                print(f"   [!] backup ก่อน retry error: {e} — ข้าม")

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

        # Watchdog: หุ่นต้อง "ขยับ" (มี velocity ใน odom) ภายใน NO_PROGRESS_TIMEOUT_SEC
        # ถอย/หมุนช้าใน recovery ก็นับว่าขยับ — กฎกรรมการคือ "ไม่คืบหน้า" = ไม่ขยับ
        # ไม่เช็ค distance_remaining เพราะ recovery อาจถอยห่าง goal ก่อนวกกลับเข้า
        start_t = time.monotonic()
        last_move_t = start_t
        aborted_by_watchdog = False
        while not nav.isTaskComplete():
            time.sleep(FEEDBACK_POLL_SEC)
            now = time.monotonic()

            if now - start_t > HARD_TIMEOUT_SEC:
                print(f"   [WATCHDOG] {name} เกิน hard timeout {HARD_TIMEOUT_SEC:.0f}s — cancel")
                nav.cancelTask()
                aborted_by_watchdog = True
                break

            fb = nav.getFeedback()
            d = fb.distance_remaining if fb is not None else float('inf')

            # ใกล้ goal — Nav2 อาจหมุนเข้า yaw_goal_tolerance ช้ามาก → skip watchdog
            if d < GOAL_APPROACH_DIST_M:
                last_move_t = now
                continue

            vel = task_nav.last_odom_vel
            if vel is None:
                # ยังไม่มี /odom — ถือว่าขยับ (กัน watchdog ตายเงียบตอนเพิ่งเริ่ม)
                moving = True
            else:
                lin_speed, ang_speed = vel
                moving = (lin_speed > ODOM_LIN_EPSILON_MPS
                          or ang_speed > ODOM_ANG_EPSILON_RPS)

            if moving:
                last_move_t = now
            elif now - last_move_t > NO_PROGRESS_TIMEOUT_SEC:
                lin_s, ang_s = vel if vel is not None else (0.0, 0.0)
                print(f"   [WATCHDOG] {name} ไม่ขยับ >{NO_PROGRESS_TIMEOUT_SEC:.0f}s "
                      f"(distance_remaining={d:.2f}m, lin={lin_s:.3f}m/s, "
                      f"ang={ang_s:.3f}rad/s) — cancel ก่อนกรรมการสั่ง retry")
                nav.cancelTask()
                aborted_by_watchdog = True
                break

        # รอ cancel เสร็จสมบูรณ์ (async) เพื่อให้ทุก state เคลียร์ก่อนรอบใหม่
        while not nav.isTaskComplete():
            time.sleep(0.05)

        result = nav.getResult()
        if aborted_by_watchdog:
            # บังคับเป็น FAILED — สงวน CANCELED ไว้สื่อ SIGTERM/Ctrl+C เท่านั้น
            # ถ้าเป็น attempt สุดท้ายแล้ว fall-through จะ return FAILED ให้ caller จัดการ
            result = TaskResult.FAILED
            print(f"   [!] {name} ค้าง (watchdog) รอบ {attempt + 1}")
            continue
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
        # ใส่ ! ต่อท้ายเลขได้ (เช่น 5!) = ไป waypoint นั้นตรงๆ ข้าม via — ใช้กับ HOME
        # เป็นหลัก เวลาหุ่นอยู่ใกล้ทางกลับแล้วไม่ต้องอ้อมผ่าน via 3 จุดของ HOME
        user_input = input("\nระบุลำดับการวิ่ง (เช่น 3,1,2 | ใส่ ! ข้าม via เช่น 5!) หรือกด 0 เพื่อเลิก: ")

        if user_input.strip() == '0':
            print("ปิดโปรแกรม...")
            break

        try:
            # แต่ละ token: เลข (1-based) + เครื่องหมาย ! ท้ายแปลว่าข้าม via
            planned_waypoints = []  # list ของ (wp, skip_via)
            for tok in user_input.split(','):
                tok = tok.strip()
                if not tok:
                    continue
                skip_via = tok.endswith('!')
                idx = int(tok.rstrip('!').strip()) - 1
                planned_waypoints.append((all_waypoints[idx], skip_via))
        except (ValueError, IndexError):
            print("[!] ใส่ตัวเลขไม่ถูกต้อง กรุณาลองใหม่")
            continue

        # เริ่มการเดินทางตามลำดับที่ป้อน
        print(f"\nเริ่มการเดินทางทั้งหมด {len(planned_waypoints)} จุด...")
        
        all_done = True  # False ถ้ามี waypoint ถูกยกเลิก/ไปไม่ถึง
        for wp, skip_via in planned_waypoints:
            # จุดคั่น (via) ถ้ามี — วิ่งผ่านก่อนโดยไม่สแกนภารกิจ
            # skip_via (เลขมี ! ต่อท้าย) = ข้าม via วิ่งตรงไป waypoint เลย
            ok = True
            via_list = [] if skip_via else wp.get('via', [])
            if skip_via and wp.get('via'):
                print(f"[ลัด] {wp['task']}: ข้าม via {len(wp['via'])} จุด — วิ่งตรง")
            for vp in via_list:
                vname = f"จุดคั่นก่อน {wp['task']} ({vp['x']}, {vp['y']})"
                result = _goto_pose(task_nav, _make_pose(nav, vp), vname)
                if result != TaskResult.SUCCEEDED:
                    ok = False
                    break
            if not ok:
                if result == TaskResult.CANCELED:
                    # ผู้ใช้ Ctrl+C / SIGTERM — หยุดทั้งแผน
                    print(f"ภารกิจไป {wp['task']} ถูกยกเลิก")
                    all_done = False
                    break
                # via fail → ข้าม WP นี้ ไปต่อ WP ถัดไป (ไม่ทิ้งทั้งแผน)
                # เสีย WP เดียวดีกว่าเสีย WP ที่เหลือทั้งหมด + ซูเปอร์บิงโก
                print(f"ไปจุดคั่นก่อน {wp['task']} ไม่ได้ — ข้าม WP นี้ ไปต่อ")
                all_done = False
                continue

            result = _goto_pose(task_nav, _make_pose(nav, wp), wp['task'])
            if result == TaskResult.SUCCEEDED:
                task_nav.perform_task(wp)
            elif result == TaskResult.CANCELED:
                # ผู้ใช้ Ctrl+C / SIGTERM — หยุดทั้งแผน
                print(f"ภารกิจไป {wp['task']} ถูกยกเลิก")
                all_done = False
                break
            else:  # FAILED (หรือ None) — ลองซ้ำครบโควต้าแล้วยังไม่ถึง
                # ข้าม WP นี้ ไปต่อ WP ถัดไป — รักษาคะแนน WP อื่น + โอกาสซูเปอร์บิงโก
                print(f"ไม่สามารถไปถึง {wp['task']} ได้ — ข้าม WP นี้ ไปต่อ")
                all_done = False
                continue

        if all_done:
            print("\n[SUCCESS] วิ่งครบตามแผนงานแล้ว!")
        else:
            print("\n[ABORT] แผนงานหยุดกลางคัน — มี waypoint ที่ไปไม่ถึง")
        print("กลับไปรอรับคำสั่งชุดใหม่...")


if __name__ == '__main__':
    main()


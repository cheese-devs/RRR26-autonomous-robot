#!/usr/bin/env python3
# encoding: utf-8

import sys, select, termios, tty, time, threading
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy
from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
from std_msgs.msg import Int32
from sensor_msgs.msg import LaserScan
from tf2_ros import TransformListener, Buffer # เพิ่ม TF
import yaml # เพิ่มสำหรับ Save YAML

# Threshold AMCL covariance (diagonal) ที่ถือว่า converged แล้ว
# ค่า x,y เป็น m^2 (std ≈ sqrt) ; yaw เป็น rad^2
AMCL_COV_XY_MAX = 0.05    # std ≈ 0.22 m
AMCL_COV_YAW_MAX = 0.07   # std ≈ 0.26 rad ≈ 15°
WARMUP_SEC = 1.5          # หยุดนิ่งก่อนอ่าน TF

msg = """
Control Your Yahboom Robot & Servo!
----------------------------------
Moving around:
    u    i    o
    j    k    l
    m    ,    .

q/z : increase/decrease max speeds by 10%
w/x : increase/decrease only linear speed by 10%
e/c : increase/decrease only angular speed by 10%

Special Actions:
    p : Run Servo Sequence (Step -40 then 0)
    s : SAVE Current Pose as Waypoint (no type)
    1 : SAVE as waypoint type=person   (flush via buffer)
    2 : SAVE as waypoint type=tag      (flush via buffer)
    0 : SAVE as HOME (task=HOME, no type)
    v : Buffer current pose as VIA point (ผูกเข้า waypoint ถัดไป)
    h : Attach buffered VIA to existing HOME in yaml (ไม่ทับ waypoint อื่น)
    b : Clear via buffer
    f : Force-save (bypass AMCL covariance check)
    a : Print AMCL status
    r : REPLACE waypoint เฉพาะตัว → กด r แล้วตามด้วย 1-9 (=waypoint_N) หรือ 0 (=HOME)
        แก้เฉพาะ x/y/orientation, preserve type+via เดิม

** BEFORE RECORDING **
  1) วางหุ่นที่ origin หันหน้า +x ก่อน launch nav2
  2) ขับวน arena 1 รอบให้ AMCL converge
  3) ทุกครั้งก่อนกด save ต้อง "หยุดนิ่ง" 1-2 วินาที (ระบบจะ warmup ให้)
  4) ถ้าเห็น "AMCL NOT CONVERGED" → อย่า save ขับวนต่อแล้ว 'a' เช็ค

CTRL-C to quit
"""

moveBindings = {
    'i': (1, 0), 'o': (1, -1), 'j': (0, 1), 'l': (0, -1),
    'u': (1, 1), ',': (-1, 0), '.': (-1, 1), 'm': (-1, -1),
}

speedBindings = {
    'q': (1.1, 1.1), 'z': (.9, .9),
    'w': (1.1, 1), 'x': (.9, 1),
    'e': (1, 1.1), 'c': (1, .9),
}

class Yahboom_Keyboard(Node):
    def __init__(self, name):
        super().__init__(name)
        self.pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.pub_servo = self.create_publisher(Int32, 'servo_s1', 10)
        self.sub_scan = self.create_subscription(LaserScan, '/scan', self.scan_callback, 10)
        # AMCL publishes /amcl_pose ด้วย TRANSIENT_LOCAL — ต้อง match ไม่งั้นพลาด latched msg แรก
        amcl_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.sub_amcl = self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self.amcl_callback, amcl_qos)

        # AMCL state
        self.amcl_cov_xx = None
        self.amcl_cov_yy = None
        self.amcl_cov_yaw = None
        self.amcl_last_time = 0.0

        # เพิ่ม TF Listener สำหรับหาตำแหน่งหุ่นยนต์
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        
        self.declare_parameter("linear_speed_limit", 1.0)
        self.declare_parameter("angular_speed_limit", 5.0)
        self.linear_speed_limit = self.get_parameter("linear_speed_limit").get_parameter_value().double_value
        self.angular_speed_limit = self.get_parameter("angular_speed_limit").get_parameter_value().double_value
        
        self.settings = termios.tcgetattr(sys.stdin)
        self.servo_busy = False
        self.waypoints = [] # เก็บ Waypoints
        self.via_buffer = [] # buffer ของ via points รอผูกเข้า waypoint ถัดไป
        self.replace_pending = False # state: รอเลขเลือก waypoint ที่จะแทน
        
        self.dist_front = 10.0
        self.dist_back  = 10.0
        self.dist_left  = 10.0
        self.dist_right = 10.0
        self.safety_limit = 0.3
        self.last_beep_time = 0.0

    def amcl_callback(self, msg):
        c = msg.pose.covariance  # row-major 6x6
        self.amcl_cov_xx = c[0]
        self.amcl_cov_yy = c[7]
        self.amcl_cov_yaw = c[35]
        self.amcl_last_time = time.time()

    def amcl_ready(self):
        """ คืน (ok: bool, reason: str) """
        if self.amcl_cov_xx is None:
            return False, "ยังไม่ได้รับ /amcl_pose เลย (Nav2 launch แล้วหรือยัง?)"
        age = time.time() - self.amcl_last_time
        if age > 5.0:
            return False, f"/amcl_pose stale ({age:.1f}s) — AMCL อาจหยุดทำงาน"
        if self.amcl_cov_xx > AMCL_COV_XY_MAX or self.amcl_cov_yy > AMCL_COV_XY_MAX:
            return False, (f"NOT CONVERGED: xx={self.amcl_cov_xx:.3f} yy={self.amcl_cov_yy:.3f} "
                          f"(max {AMCL_COV_XY_MAX}) → ขับวนต่อให้ AMCL converge")
        if self.amcl_cov_yaw > AMCL_COV_YAW_MAX:
            return False, (f"yaw NOT CONVERGED: yaw_cov={self.amcl_cov_yaw:.3f} "
                          f"(max {AMCL_COV_YAW_MAX}) → หมุนกลับไปกลับมาช่วย converge")
        return True, "OK"

    def print_amcl_status(self):
        if self.amcl_cov_xx is None:
            print("\n[AMCL] no /amcl_pose received")
            return
        ok, reason = self.amcl_ready()
        tag = "READY" if ok else "BAD"
        import math
        sx = math.sqrt(max(self.amcl_cov_xx, 0))
        sy = math.sqrt(max(self.amcl_cov_yy, 0))
        sth = math.sqrt(max(self.amcl_cov_yaw, 0))
        print(f"\n[AMCL {tag}] std σx={sx:.3f}m σy={sy:.3f}m σθ={math.degrees(sth):.1f}° — {reason}")

    def scan_callback(self, msg):
        num_points = len(msg.ranges)
        b_idx = list(range(0, 31)) + list(range(num_points-30, num_points))
        r_idx = list(range(60, 121))
        f_idx = list(range(150, 211))
        l_idx = list(range(240, 301))

        def get_min_dist(indices):
            ranges = [msg.ranges[i] for i in indices if i < len(msg.ranges) and 0.05 < msg.ranges[i] < 3.0]
            return min(ranges) if ranges else 10.0

        self.dist_front = get_min_dist(f_idx)
        self.dist_left  = get_min_dist(l_idx)
        self.dist_back  = get_min_dist(b_idx)
        self.dist_right = get_min_dist(r_idx)

    def save_waypoint(self, wp_type=None, is_home=False, force=False):
        """ ดึงตำแหน่งปัจจุบันจาก TF แล้วบันทึกลง YAML
            wp_type: 'person' | 'tag' | None
            is_home: True = task='HOME' (ไม่ใส่ type ไม่นับเลข)
            force: True = ข้าม AMCL covariance check
        """
        if not force:
            ok, reason = self.amcl_ready()
            if not ok:
                print(f"\n[REJECT save] {reason}")
                print("  → ขับวนต่อจนกว่า cov ลง หรือกด 'f' เพื่อ force save")
                return
        # หยุดนิ่งและ warmup ให้ AMCL settle ก่อนอ่าน TF
        print(f"\n[warmup] หยุดนิ่ง {WARMUP_SEC:.1f}s ให้ AMCL settle...", end='', flush=True)
        self.pub.publish(Twist())  # zero cmd_vel
        t0 = time.time()
        while time.time() - t0 < WARMUP_SEC:
            rclpy.spin_once(self, timeout_sec=0.05)
        print(" done")
        try:
            now = rclpy.time.Time()
            trans = self.tf_buffer.lookup_transform('map', 'base_link', now,
                                                    timeout=rclpy.duration.Duration(seconds=0.2))

            pos = trans.transform.translation
            ori = trans.transform.rotation

            if is_home:
                wp_data = {'task': 'HOME'}
            else:
                w_idx = sum(1 for w in self.waypoints if w.get('task', '').startswith('waypoint_')) + 1
                wp_data = {'task': f'waypoint_{w_idx}'}
                if wp_type:
                    wp_data['type'] = wp_type

            wp_data['x'] = round(pos.x, 3)
            wp_data['y'] = round(pos.y, 3)
            wp_data['orientation'] = {
                'z': round(ori.z, 5),
                'w': round(ori.w, 5),
            }

            # ผูก via ที่ buffered ไว้เข้ากับ waypoint ที่กำลังเซฟ — รวมถึง HOME
            if self.via_buffer:
                wp_data['via'] = self.via_buffer
                via_n = len(self.via_buffer)
                self.via_buffer = []
            else:
                via_n = 0

            self.waypoints.append(wp_data)

            with open('nav_waypoints.yaml', 'w') as f:
                yaml.dump({'waypoints': self.waypoints}, f, sort_keys=False)

            tag = 'HOME' if is_home else wp_data.get('type', '-')
            via_msg = f" +via×{via_n}" if via_n else ""
            print(f"\n[SAVED] {wp_data['task']} ({tag}) at x:{wp_data['x']}, y:{wp_data['y']}{via_msg}")

        except Exception as e:
            print(f"\n[ERROR] Could not save waypoint: {e}")

    def buffer_via(self, force=False):
        """ เก็บตำแหน่งปัจจุบันเข้า via buffer (ยังไม่เขียนไฟล์) """
        if not force:
            ok, reason = self.amcl_ready()
            if not ok:
                print(f"\n[REJECT via] {reason}")
                return
        try:
            now = rclpy.time.Time()
            trans = self.tf_buffer.lookup_transform('map', 'base_link', now,
                                                    timeout=rclpy.duration.Duration(seconds=0.2))
            pos = trans.transform.translation
            ori = trans.transform.rotation
            via = {
                'x': round(pos.x, 3),
                'y': round(pos.y, 3),
                'orientation': {
                    'z': round(ori.z, 5),
                    'w': round(ori.w, 5),
                }
            }
            self.via_buffer.append(via)
            print(f"\n[VIA] buffered #{len(self.via_buffer)} at x:{via['x']}, y:{via['y']}")
        except Exception as e:
            print(f"\n[ERROR] Could not buffer via: {e}")

    def clear_via(self):
        n = len(self.via_buffer)
        self.via_buffer = []
        print(f"\n[VIA] cleared {n} buffered point(s)")

    def attach_via_to_home(self):
        """ ผูก via_buffer เข้ากับ entry HOME ใน yaml ที่มีอยู่แล้ว
            โหลด → แก้เฉพาะ HOME → save กลับ — waypoint อื่นไม่กระทบ
        """
        if not self.via_buffer:
            print("\n[REJECT attach] via buffer ว่าง — กด 'v' บัฟเฟอร์จุดก่อน")
            return
        try:
            with open('nav_waypoints.yaml', 'r') as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print("\n[ERROR] ไม่พบ nav_waypoints.yaml — ต้องมี HOME ในไฟล์อยู่ก่อน")
            return
        except Exception as e:
            print(f"\n[ERROR] โหลด yaml ไม่ได้: {e}")
            return

        wps = data.get('waypoints', [])
        home = next((w for w in wps if w.get('task', '').upper() == 'HOME'), None)
        if home is None:
            print("\n[ERROR] ไม่เจอ entry task=HOME ใน yaml — เซฟ HOME ก่อน ('0')")
            return

        home['via'] = self.via_buffer
        n = len(self.via_buffer)
        try:
            with open('nav_waypoints.yaml', 'w') as f:
                yaml.dump({'waypoints': wps}, f, sort_keys=False)
        except Exception as e:
            print(f"\n[ERROR] เขียน yaml ไม่ได้: {e}")
            return

        self.via_buffer = []
        # sync ของใน memory ให้ตรง disk — ถ้าผู้ใช้กดเซฟต่อจะได้ไม่ทับของที่เพิ่ง attach
        self.waypoints = wps
        print(f"\n[ATTACH] ผูก via×{n} เข้ากับ HOME แล้ว — waypoint อื่นคงเดิม")

    def replace_waypoint(self, idx, force=False):
        """ แทนที่พิกัดของ waypoint ที่มีอยู่แล้วใน yaml
            idx: 0 = HOME, 1-9 = waypoint_N
            preserve: task, type, via — แก้แค่ x/y/orientation
        """
        if not force:
            ok, reason = self.amcl_ready()
            if not ok:
                print(f"\n[REJECT replace] {reason}")
                return

        # โหลด yaml ปัจจุบัน
        try:
            with open('nav_waypoints.yaml', 'r') as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print("\n[ERROR] ไม่พบ nav_waypoints.yaml — ยังไม่มีอะไรให้แทน")
            return
        except Exception as e:
            print(f"\n[ERROR] โหลด yaml ไม่ได้: {e}")
            return

        wps = data.get('waypoints', []) or []
        target_task = 'HOME' if idx == 0 else f'waypoint_{idx}'
        target = next((w for w in wps if w.get('task', '').upper() == target_task.upper()), None)
        if target is None:
            print(f"\n[ERROR] ไม่เจอ '{target_task}' ใน yaml")
            return

        # warmup ให้ AMCL settle ก่อนอ่าน TF
        print(f"\n[warmup] หยุดนิ่ง {WARMUP_SEC:.1f}s ให้ AMCL settle...", end='', flush=True)
        self.pub.publish(Twist())
        t0 = time.time()
        while time.time() - t0 < WARMUP_SEC:
            rclpy.spin_once(self, timeout_sec=0.05)
        print(" done")

        try:
            now = rclpy.time.Time()
            trans = self.tf_buffer.lookup_transform('map', 'base_link', now,
                                                    timeout=rclpy.duration.Duration(seconds=0.2))
            pos = trans.transform.translation
            ori = trans.transform.rotation

            old_x, old_y = target.get('x'), target.get('y')
            target['x'] = round(pos.x, 3)
            target['y'] = round(pos.y, 3)
            target['orientation'] = {
                'z': round(ori.z, 5),
                'w': round(ori.w, 5),
            }

            with open('nav_waypoints.yaml', 'w') as f:
                yaml.dump({'waypoints': wps}, f, sort_keys=False)

            # sync memory ให้ตรง disk
            self.waypoints = wps

            kept = []
            if 'type' in target:
                kept.append(f"type={target['type']}")
            if 'via' in target:
                kept.append(f"via×{len(target['via'])}")
            kept_msg = f" — preserve {', '.join(kept)}" if kept else ""
            print(f"\n[REPLACE] {target_task}: ({old_x},{old_y}) → ({target['x']},{target['y']}){kept_msg}")

        except Exception as e:
            print(f"\n[ERROR] อ่าน TF ไม่ได้: {e}")

    def play_warning_sound(self):
        current_time = time.time()
        if current_time - self.last_beep_time > 0.5:
            sys.stdout.write('\a')
            sys.stdout.flush()
            self.last_beep_time = current_time
    
    def getKey(self):
        tty.setraw(sys.stdin.fileno())
        rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
        if rlist:
            key = sys.stdin.read(1)
        else:
            key = ''
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
        return key

    def run_servo_sequence(self):
        self.servo_busy = True
        msg_servo = Int32(data=-40)
        self.pub_servo.publish(msg_servo)
        time.sleep(1.0)
        msg_servo.data = 0
        self.pub_servo.publish(msg_servo)
        self.servo_busy = False
        
    def vels(self, speed, turn):
        return f"currently:\tspeed {speed:.2f}\tturn {turn:.2f}"

def main():
    rclpy.init()
    node = Yahboom_Keyboard("yahboom_keyboard_ctrl")
    
    (speed, turn) = (0.15, 0.8)
    (x, th) = (0, 0)
    status = 0
    count = 0

    try:
        print(msg)
        print(node.vels(speed, turn))
        
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.01)
            key = node.getKey()

            # --- replace mode: ดักเลขก่อน handler ปกติ ---
            # หลังกด 'r' รอบนึง คีย์ถัดไปที่เป็นเลข = แทน waypoint นั้น
            # คีย์อื่นที่ไม่ใช่ '' = ยกเลิก replace mode
            if node.replace_pending and key != '':
                if key in '0123456789':
                    node.replace_waypoint(int(key))
                    node.replace_pending = False
                    key = ''  # consume กัน handler อื่นทำซ้ำ
                else:
                    print("\n[REPLACE] ยกเลิก")
                    node.replace_pending = False
                    # ปล่อย key ให้ handler อื่นทำงานต่อ

            # --- ตรวจสอบปุ่มกดพิเศษ ---
            if key == 'p':
                if not node.servo_busy:
                    threading.Thread(target=node.run_servo_sequence).start()

            elif key == 's': # กด s เพื่อเซฟตำแหน่ง (ไม่มี type)
                node.save_waypoint()
            elif key == '1': # save type=person
                node.save_waypoint(wp_type='person')
            elif key == '2': # save type=tag
                node.save_waypoint(wp_type='tag')
            elif key == '0': # save HOME
                node.save_waypoint(is_home=True)
            elif key == 'r': # เข้า replace mode → รอเลขเลือก waypoint
                node.replace_pending = True
                print("\n[REPLACE] กด 1-9 = แทน waypoint_N, 0 = แทน HOME, อื่นๆ = ยกเลิก")
            elif key == 'v': # buffer via point
                node.buffer_via()
            elif key == 'b': # clear via buffer
                node.clear_via()
            elif key == 'h': # attach buffered via to existing HOME (โหลด→แก้→เซฟ)
                node.attach_via_to_home()
            elif key == 'a': # AMCL status
                node.print_amcl_status()
            elif key == 'f': # force-save แบบไม่ระบุ type (ข้าม AMCL check)
                node.save_waypoint(force=True)

            # --- Logic การเคลื่อนที่ ---
            if key in moveBindings.keys():
                x, th = moveBindings[key]
                count = 0
            elif key in speedBindings.keys():
                speed = min(speed * speedBindings[key][0], node.linear_speed_limit)
                turn = min(turn * speedBindings[key][1], node.angular_speed_limit)
                print(node.vels(speed, turn))
                count = 0
            elif key == ' ' or key == 'k':
                x, th = 0, 0
            elif key == '\x03': # CTRL-C
                break
            else:
                count += 1
                if count > 4:
                    x, th = 0, 0

            # --- ระบบความปลอดภัย (Safety System) ---
            twist = Twist()
            target_linear = speed * x
            target_angular = turn * th
            is_blocked = False

            if x > 0 and node.dist_front < node.safety_limit:
                target_linear, is_blocked = 0.0, True
            elif x < 0 and node.dist_back < node.safety_limit:
                target_linear, is_blocked = 0.0, True

            if th > 0 and node.dist_left < node.safety_limit:
                target_angular, is_blocked = 0.0, True
            elif th < 0 and node.dist_right < node.safety_limit:
                target_angular, is_blocked = 0.0, True
                
            if is_blocked:
                node.play_warning_sound()
                
            twist.linear.x = float(target_linear)
            twist.angular.z = float(target_angular)
            node.pub.publish(twist)
            sys.stdout.flush()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        node.pub.publish(Twist())
        node.pub_servo.publish(Int32(data=0))
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, node.settings)
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

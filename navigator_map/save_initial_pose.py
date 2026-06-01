#!/usr/bin/env python3
# ฟัง /initialpose จาก RViz (ปุ่ม "2D Pose Estimate")
# แล้วเขียน x, y, yaw กลับเข้า prarams/dwb_nav_params.yaml ให้อัตโนมัติ
#
# วิธีใช้:
#   1. วางหุ่นที่จุดสตาร์ทใหม่จริงๆ ในสนาม
#   2. เปิด Nav2:           ros2 launch nav2_launch.py
#   3. เปิดสคริปต์นี้:       python3 save_initial_pose.py
#   4. ใน RViz กด "2D Pose Estimate" คลิก-ลากตำแหน่ง+ทิศของหุ่น
#   5. yaml ถูกอัปเดตทันที — ครั้งหน้าเปิด Nav2 จะใช้ initial_pose นี้เลย

import math
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseWithCovarianceStamped

PARAMS_PATH = Path(__file__).parent / 'prarams' / 'dwb_nav_params.yaml'


def quat_to_yaw(z: float, w: float) -> float:
    # planar pose จาก RViz มีแค่ qz, qw ที่ไม่เป็นศูนย์
    return 2.0 * math.atan2(z, w)


def update_initial_pose_in_yaml(x: float, y: float, yaw: float) -> None:
    # เขียนแบบ line-based เพื่อไม่ทำลาย comment/format ในไฟล์ params
    lines = PARAMS_PATH.read_text().splitlines(keepends=True)
    in_block = False
    block_indent = -1
    fields_updated = {'x': False, 'y': False, 'yaw': False}

    for i, line in enumerate(lines):
        stripped = line.strip()
        cur_indent = len(line) - len(line.lstrip())

        if not in_block:
            if stripped == 'initial_pose:':
                in_block = True
                block_indent = cur_indent
            continue

        # ออกจาก block เมื่อเจอบรรทัดที่ indent ตื้นกว่าหรือเท่ากับ initial_pose
        if stripped and cur_indent <= block_indent:
            break

        pad = ' ' * cur_indent
        if stripped.startswith('x:'):
            lines[i] = f'{pad}x: {x:.4f}\n'
            fields_updated['x'] = True
        elif stripped.startswith('y:'):
            lines[i] = f'{pad}y: {y:.4f}\n'
            fields_updated['y'] = True
        elif stripped.startswith('yaw:'):
            lines[i] = f'{pad}yaw: {yaw:.4f}\n'
            fields_updated['yaw'] = True

    missing = [k for k, v in fields_updated.items() if not v]
    if missing:
        raise RuntimeError(f'ไม่เจอ field {missing} ใน block initial_pose: ของ {PARAMS_PATH}')

    PARAMS_PATH.write_text(''.join(lines))


class InitialPoseSaver(Node):
    def __init__(self):
        super().__init__('initial_pose_saver')
        self.create_subscription(
            PoseWithCovarianceStamped, '/initialpose', self.cb, 10
        )
        self.get_logger().info(f'ฟัง /initialpose → เขียนกลับเข้า {PARAMS_PATH}')
        self.get_logger().info('ใน RViz กด "2D Pose Estimate" คลิก-ลากตำแหน่งหุ่น')

    def cb(self, msg: PoseWithCovarianceStamped):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = quat_to_yaw(q.z, q.w)
        deg = math.degrees(yaw)

        try:
            update_initial_pose_in_yaml(p.x, p.y, yaw)
        except Exception as e:
            self.get_logger().error(f'เขียน yaml ไม่สำเร็จ: {e}')
            return

        self.get_logger().info(
            f'[SAVED] x={p.x:.3f}, y={p.y:.3f}, yaw={yaw:.4f} rad ({deg:.1f}°) '
            f'→ {PARAMS_PATH.name}'
        )


def main():
    rclpy.init()
    node = InitialPoseSaver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# encoding: utf-8

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from cv_bridge import CvBridge
from sensor_msgs.msg import CompressedImage
import cv2 as cv
import numpy as np
import apriltag # สำหรับ AprilTag

class MY_Picture(Node):
    def __init__(self, name):
        super().__init__(name)
        self.bridge = CvBridge()
        self.sub_img = self.create_subscription(
            CompressedImage, '/espRos/esp32camera', self.handleTopic, 1)

        # ตั้งค่า AprilTag (ตระกูล tag36h11)
        options = apriltag.DetectorOptions(families="tag36h11")
        self.at_detector = apriltag.Detector(options)
        self.pub_at_id = self.create_publisher(String, '/vision/latest_at_id', 10)

        # pre-warm — โหลด detector graph ตั้งแต่ start (ตอน robot ยัง navigate / CPU ว่าง)
        # ครั้งแรกที่ at_detector.detect() ถูกเรียกจะ JIT โหลด → ถ้าไม่ warm จะช้าตอน waypoint แรก
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.at_detector.detect(cv.cvtColor(dummy, cv.COLOR_BGR2GRAY))
        self.get_logger().info("[VISION] pre-warm AprilTag เสร็จ พร้อม detect")

        # toggle ให้ navigator เปิด/ปิด detection — default OFF ลด CPU ตอน navigate
        # person waypoint ไม่ใช้กล้อง (ปล่อย servo ทันที) → enable เฉพาะ tag waypoint
        self.detect_enabled = False
        self.sub_enable = self.create_subscription(
            Bool, '/vision/detect_enable', self._on_enable, 10)

        # ข้อมูลล่าสุด (ค้างไว้สำหรับ log)
        self.latest_at_id = "Waiting for Tag..."

    def _on_enable(self, msg):
        if msg.data != self.detect_enabled:
            self.get_logger().info(f"[VISION] detect_enabled → {msg.data}")
        self.detect_enabled = msg.data

    def handleTopic(self, msg):
        # 1. รับภาพและปรับขนาด — กัน JPEG เสียจาก UDP fragment (ทิ้ง frame เสีย ไม่ให้ node ตาย)
        try:
            frame = self.bridge.compressed_imgmsg_to_cv2(msg)
        except Exception as e:
            self.get_logger().warn(f"decode JPEG ล้มเหลว ข้าม frame: {e}")
            return
        if frame is None or frame.size == 0:
            self.get_logger().warn("frame ว่าง/เสีย ข้าม")
            return
        try:
            frame = cv.resize(frame, (640, 480))
        except cv.error as e:
            self.get_logger().warn(f"resize ล้มเหลว ข้าม frame: {e}")
            return

        # 2. ตรวจจับ AprilTag (เปิดเฉพาะตอน navigator สั่ง — tag waypoint)
        # ไม่ imshow แล้ว — ภาพสดดูจากไฟล์อื่น, อ่าน ID จาก log navigator (mission_script print)
        # เหลือแค่ detect → publish /vision/latest_at_id + log ID ไว้เป็นหลักฐานใน vision.log
        if self.detect_enabled:
            gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
            tags = self.at_detector.detect(gray)
            for tag in tags:
                self.latest_at_id = f"ID: {tag.tag_id}"
                at_msg = String()
                at_msg.data = str(tag.tag_id)
                self.pub_at_id.publish(at_msg)
                self.get_logger().info(f"[VISION] เจอ AprilTag {self.latest_at_id}")

def main():
    print("Initializing Multi-Vision System...")
    rclpy.init()
    node = MY_Picture("Yahboom_Vision_Node")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

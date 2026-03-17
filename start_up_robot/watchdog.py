#!/usr/bin/env python3
# encoding: utf-8

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Imu
import time

class SystemWatchdog(Node):
    def __init__(self):
        super().__init__('system_watchdog')
        
        self.last_cam_time = time.time()
        self.last_imu_time = time.time()
        self.last_imu_z = 0.0
        self.imu_active = False
        
        # Subscribe กล้อง และ IMU
        self.sub_cam = self.create_subscription(CompressedImage, '/espRos/esp32camera', self.cam_callback, 10)
        self.sub_imu = self.create_subscription(Imu, '/imu', self.imu_callback, 10)
            
        self.timer = self.create_timer(1.0, self.check_status)
        
        print("\n" + "="*45)
        print("   YAHBOOM SYSTEM WATCHDOG (IMU Z-CHECK)")
        print("="*45)

    def cam_callback(self, msg):
        self.last_cam_time = time.time()

    def imu_callback(self, msg):
        # บันทึกเวลาล่าสุดที่ได้รับข้อมูล
        self.last_imu_time = time.time()
        # เก็บค่าแกน Z ไว้ตรวจสอบ
        self.last_imu_z = msg.linear_acceleration.z
        
        # Logic: ถ้าแกน Z ไม่เป็น 0 แสดงว่าเซนเซอร์ทำงานปกติ (มีแรงโน้มถ่วงโลก)
        if abs(self.last_imu_z) > 0.1:
            self.imu_active = True
        else:
            self.imu_active = False

    def check_status(self):
        now = time.time()
        
        # 1. เช็คกล้อง (ขาดหายเกิน 2 วิ)
        cam_alive = (now - self.last_cam_time) < 2.0
        
        # 2. เช็ค IMU (ต้องมีข้อมูลมา และ แกน Z ต้องไม่เป็น 0)
        imu_com_alive = (now - self.last_imu_time) < 2.0
        imu_functional = imu_com_alive and self.imu_active
        
        GREEN = '\033[92m'
        RED = '\033[91m'
        RESET = '\033[0m'
        
        cam_status = f"{GREEN}ONLINE{RESET}" if cam_alive else f"{RED}OFFLINE{RESET}"
        
        # แสดงสถานะ IMU โดยแยกกรณีหลุด (Com) กับกรณีเซนเซอร์พัง (Z=0)
        if not imu_com_alive:
            imu_status = f"{RED}OFFLINE (No Data){RESET}"
        elif not self.imu_active:
            imu_status = f"{RED}OFFLINE (Sensor Fault / Z=0){RESET}"
        else:
            imu_status = f"{GREEN}ONLINE (IMU.Z: {self.last_imu_z:.2f}){RESET}"
        
        print(f"[{time.strftime('%H:%M:%S')}] Cam: {cam_status:25} | ROBOT: {imu_status}")

def main():
    rclpy.init()
    node = SystemWatchdog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

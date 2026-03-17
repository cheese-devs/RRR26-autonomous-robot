import serial
import time

def setup_wifi_module():
    # ls /dev/ttyUSB*  # ตรวจสอบรายชื่อ ttyUSB ทั้งหมด
    # ถ้ามองไม่เห็น /dev/ttyUSB0
    # sudo apt remove brltty -y #ลบ Service ที่แย่งพอร์ตออก
    # sudo modprobe ch341 #ถอดสาย USB ออกแล้วเสียบใหม่ หรือใช้คำสั่งบังคับให้ระบบโหลด Driver ใหม่
    port = '/dev/ttyUSB0' 
    baudrate = 115200
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"Connected to {port} at {baudrate} baud")
        
        # รายการคำสั่งที่ต้องการส่ง
        '''
        commands = [
            "wifi_mode:1",              # ตั้งเป็น Station Mode
            "sta_ssid:robot-wifi-1",        # ชื่อ WiFi
            "sta_pd:123456789-0",     # รหัสผ่าน
            "ros2_ip:<REDACTED-IP>",    # IP เครื่องรับ (คอมพิวเตอร์)
            "domain_id:20",		#domainid of ROS2
            "wifi_ver"                 # ตรวจสอบเวอร์ชั่น
        ]
        '''
        # เลือกเฉพาะ domainid
        commands = [
            "wifi_mode:1",
            "domain_id:20", 	# กำหนด domainid of ROS2
        ]
        
        for cmd in commands:
            # ส่งคำสั่งพร้อมปิดท้ายด้วย \r\n (Enter) ตามมาตรฐาน AT Command
            full_cmd = cmd + "\r\n"
            ser.write(full_cmd.encode('utf-8'))
            
            print(f"Sending: {cmd}")
            
            # รออ่านผลลัพธ์จากโมดูล
            time.sleep(1)
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                print(f"Response: {response.strip()}")
                
        ser.close()
        print("Configuration Complete.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    setup_wifi_module()

#!/usr/bin/env bash
# find_camera.sh — สแกนหา IP กล้อง (docker) ในเครือข่าย
# กล้อง listen พอร์ต TCP 8888 (ดู SET_Camera.py)
# วิธีใช้:
#   ./find_camera.sh                  # สแกนวงที่เครื่องต่ออยู่ + 192.168.1.x
#   ./find_camera.sh 192.168.4        # สแกน subnet ที่ระบุเพิ่ม (เว้น octet สุดท้าย)
#   PORT=8888 TIMEOUT=0.3 ./find_camera.sh

PORT="${PORT:-8888}"          # พอร์ตที่กล้องเปิดไว้
TIMEOUT="${TIMEOUT:-0.3}"     # timeout ต่อ host (วินาที)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

# --- รวบรวม subnet ที่จะสแกน (เก็บแค่ /24 prefix เช่น "192.168.1") ---
declare -A subnets

# 1) subnet ที่เครื่องนี้ต่ออยู่ (ข้าม loopback กับ docker bridge 172.17.x)
while read -r ip; do
    [[ "$ip" == 127.* || "$ip" == 172.17.* ]] && continue
    subnets["${ip%.*}"]=1
done < <(ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1)

# 2) subnet default ของกล้องตาม SET_Camera.py
subnets["192.168.1"]=1

# 3) subnet ที่ผู้ใช้ระบุผ่าน argument
for arg in "$@"; do
    subnets["$arg"]=1
done

echo -e "${YELLOW}สแกนหากล้อง — พอร์ต ${PORT}, timeout ${TIMEOUT}s/host${NC}"
echo "subnet ที่จะสแกน: ${!subnets[*]}"
echo "----------------------------------------"

found=()
for net in "${!subnets[@]}"; do
    echo -e "→ กำลังสแกน ${net}.1-254 ..."
    results=$(mktemp)
    for i in $(seq 1 254); do
        host="${net}.${i}"
        (
            if timeout "$TIMEOUT" bash -c "echo > /dev/tcp/${host}/${PORT}" 2>/dev/null; then
                echo "$host" >> "$results"
            fi
        ) &
    done
    wait
    while read -r hit; do
        found+=("$hit")
        echo -e "  ${GREEN}✔ พบอุปกรณ์เปิดพอร์ต ${PORT}: ${hit}${NC}"
    done < "$results"
    rm -f "$results"
done

echo "----------------------------------------"
if [ ${#found[@]} -eq 0 ]; then
    echo -e "${RED}✘ ไม่พบกล้อง${NC}"
    echo "  - ตรวจว่าต่อ WiFi วงเดียวกับหุ่น/กล้องแล้ว"
    echo "  - ตรวจว่า docker บนกล้องรันอยู่"
    echo "  - ลองระบุ subnet เอง เช่น: ./find_camera.sh 192.168.0"
    exit 1
else
    echo -e "${GREEN}พบ ${#found[@]} อุปกรณ์ที่เปิดพอร์ต ${PORT}:${NC}"
    for f in "${found[@]}"; do echo "  $f"; done
    echo
    echo "นำ IP ไปกรอกตอน SET_Camera.py ถาม 'please input docket ipV4:'"
fi

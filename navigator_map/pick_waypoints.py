#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
เครื่องมือเก็บ waypoint แบบคลิกบนแผนที่ — ไม่ต้องวิ่งหุ่นจริง (Tkinter version)

วิธีใช้:
    cd navigator_map
    python3 pick_waypoints.py

กติกาคลิก (บนภาพแผนที่):
    ซ้ายคลิก 2 ครั้ง   → เพิ่ม waypoint (คลิก1 = ตำแหน่ง, คลิก2 = ทิศหุ่น)
    ขวาคลิก 2 ครั้ง   → เพิ่ม via point (เข้า buffer)
                        คลิกซ้าย-pair ถัดไป → via ที่ค้าง buffer ผูกกับ wp นั้น
    ลากจุดเดิม         → คลิกซ้ายค้างบนจุด wp/via ที่วางแล้ว แล้วลากไปตำแหน่งใหม่
                        (คงทิศหุ่นเดิม, snap 5cm ตามเดิม)
    Shift+ลากจุดเดิม   → หมุนทิศหุ่นของจุดนั้น (ตรึงตำแหน่ง, ลากชี้ไปทางที่อยากให้หัวหุ่นหัน)
ปุ่มบนหน้าจอ:
    Person / Tag / HOME → เลือก type ของ waypoint ถัดไป
    Undo / Clear via    → ย้อน / ล้าง buffer
    Save / Save & Quit  → เซฟลง nav_waypoints.yaml

หมายเหตุ:
- ถ้ามี nav_waypoints.yaml อยู่แล้ว จะโหลด waypoint เดิมขึ้นมาให้ลากแก้ได้ทันที
- พิกัด world คำนวณจาก resolution + origin ใน my_robot_map.yaml
- yaw คำนวณจาก atan2(y2-y1, x2-x1) → quaternion (z,w)
- จะสำรองไฟล์เดิมเป็น nav_waypoints.yaml.bak ก่อน overwrite
"""

import math
import os
import shutil
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import yaml

MAP_YAML = "my_robot_map.yaml"
OUT_YAML = "nav_waypoints.yaml"
PX_PER_M = 200  # ใช้เป็น fallback ถ้าคำนวณจากขนาดจอไม่ได้
SCREEN_MARGIN_PX = 160  # เผื่อ taskbar + toolbar + status
SNAP_GRID = 0.05  # snap คลิก/เล็ง เป็นช่องละ 5cm (= resolution map)


def load_map(yaml_path):
    with open(yaml_path) as f:
        meta = yaml.safe_load(f)
    res = float(meta["resolution"])
    ox, oy = float(meta["origin"][0]), float(meta["origin"][1])
    img_path = meta["image"]
    if not os.path.isabs(img_path):
        img_path = os.path.join(os.path.dirname(os.path.abspath(yaml_path)), img_path)
    with open(img_path, "rb") as f:
        magic = f.readline().strip()
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        w, h = map(int, line.split())
        maxval = int(f.readline().strip())
        if magic == b"P5":
            dtype = np.uint8 if maxval < 256 else np.uint16
            data = np.frombuffer(f.read(), dtype=dtype).reshape(h, w)
        elif magic == b"P2":
            data = np.array(f.read().split(), dtype=int).reshape(h, w)
        else:
            raise RuntimeError(f"PGM format not supported: {magic}")
    return data, res, (ox, oy), (w, h)


def yaw_to_quat(yaw):
    return float(math.sin(yaw / 2.0)), float(math.cos(yaw / 2.0))


def pose_dict(x, y, yaw):
    z, w = yaw_to_quat(yaw)
    return {
        "x": round(float(x), 3),
        "y": round(float(y), 3),
        "orientation": {"z": round(z, 5), "w": round(w, 5)},
    }


class Picker:
    TYPE_COLORS = {"person": "red", "tag": "blue", "HOME": "green"}

    def __init__(self, root, map_data, res, origin, map_size):
        self.root = root
        self.res = res
        self.ox, self.oy = origin
        self.map_w_px, self.map_h_px = map_size  # in original pgm pixels

        # คำนวณ scale: 1 cell PGM = SCALE หน้าจอ pixel — ปรับให้พอดีจอ
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight() - SCREEN_MARGIN_PX
        scale_fit = max(1, min(sw // self.map_w_px, sh // self.map_h_px))
        self.scale = max(int(PX_PER_M * res), scale_fit)
        self.canvas_w = self.map_w_px * self.scale
        self.canvas_h = self.map_h_px * self.scale

        self.waypoints = []
        self.via_buffer = []
        self.pending = None  # ('wp'|'via', wx, wy)
        self.next_type = "person"
        self.artists = []  # [('wp'|'via'|'pending', [canvas_ids])]
        self.markers = []  # [{kind, ids, pose}] — จุดที่วางแล้ว (ลากย้ายได้)
        self.dragging = None  # marker ที่กำลังลากอยู่
        self.drag_mode = "move"  # 'move' (ลากเปล่า) | 'rotate' (Shift+ลาก)
        self.route_ids = []  # เส้นเชื่อมแต่ละช่วง (segment) — คนละสี

        self._build_ui()
        self._render_map(map_data)
        self._load_existing()
        self._update_status()

    def _build_ui(self):
        self.root.title("Waypoint Picker — คลิกซ้าย=wp, คลิกขวา=via")

        top = ttk.Frame(self.root)
        top.pack(side="top", fill="x", padx=4, pady=4)

        self.type_var = tk.StringVar(value=self.next_type)
        ttk.Label(top, text="Type ถัดไป:").pack(side="left")
        for t in ("person", "tag", "HOME"):
            ttk.Radiobutton(top, text=t, value=t, variable=self.type_var,
                            command=self._on_type_change).pack(side="left", padx=2)

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        self.snap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Snap 5cm (g)", variable=self.snap_var).pack(side="left", padx=4)
        self.root.bind("<Key-g>", lambda e: self.snap_var.set(not self.snap_var.get()))

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(top, text="Undo", command=self.undo).pack(side="left", padx=2)
        ttk.Button(top, text="Clear via", command=self.clear_via).pack(side="left", padx=2)
        ttk.Button(top, text="Save", command=self.save).pack(side="left", padx=2)
        ttk.Button(top, text="Save & Quit", command=self.save_and_quit).pack(side="left", padx=2)

        ttk.Label(top, text="ลากจุด=ย้าย · Shift+ลาก=หมุนทิศ",
                  foreground="#666").pack(side="right", padx=6)

        self.status = ttk.Label(self.root, text="", anchor="w")
        self.status.pack(side="bottom", fill="x", padx=4, pady=2)

        self.canvas = tk.Canvas(self.root, width=self.canvas_w, height=self.canvas_h,
                                bg="white", highlightthickness=1, highlightbackground="gray")
        self.canvas.pack(side="top", padx=4, pady=4)

        self.canvas.bind("<Button-1>", lambda e: self.on_click(e, button=1))
        self.canvas.bind("<Button-3>", lambda e: self.on_click(e, button=3))
        self.canvas.bind("<Motion>", self.on_motion)
        # ลากย้ายจุดที่วางแล้ว (คลิกซ้ายค้างบนจุดเดิมแล้วลาก)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # จุดเล็ง: เส้นกากบาทตามเมาส์ + พิกัดลอย + เส้นยางพรีวิวทิศ
        self.cross_v = self.canvas.create_line(0, 0, 0, 0, fill="#1e90ff", dash=(3, 3))
        self.cross_h = self.canvas.create_line(0, 0, 0, 0, fill="#1e90ff", dash=(3, 3))
        self.cursor_txt = self.canvas.create_text(0, 0, text="", anchor="sw",
                                                  fill="#0066cc", font=("TkDefaultFont", 9, "bold"))
        self.rubber = None

    def _on_type_change(self):
        self.next_type = self.type_var.get()
        self._update_status()

    # ---------- coordinate conversion ----------
    # canvas pixel (cx, cy) → world (wx, wy)
    # PGM: ภาพแถวบน=y สูง (origin บนซ้ายของ image), แต่ ROS origin คือ bottom-left
    # wx = ox + (cx / scale) * res
    # wy = oy + ((H_px - cy/scale)) * res   (canvas y โต = ลง = wy ต่ำ)
    def canvas_to_world(self, cx, cy):
        col = cx / self.scale
        row_from_bottom = self.map_h_px - (cy / self.scale)
        wx = self.ox + col * self.res
        wy = self.oy + row_from_bottom * self.res
        return wx, wy

    def _snap(self, wx, wy):
        if self.snap_var.get():
            return round(wx / SNAP_GRID) * SNAP_GRID, round(wy / SNAP_GRID) * SNAP_GRID
        return wx, wy

    def world_to_canvas(self, wx, wy):
        col = (wx - self.ox) / self.res
        row_from_bottom = (wy - self.oy) / self.res
        cx = col * self.scale
        cy = (self.map_h_px - row_from_bottom) * self.scale
        return cx, cy

    # ---------- map rendering ----------
    def _render_map(self, map_data):
        # ใช้ PhotoImage ขยาย (ทุกพิกเซลขยายเป็น scale x scale)
        # สร้าง grayscale PPM แล้ว PhotoImage จะอ่านได้
        s = self.scale
        h, w = map_data.shape
        big = np.repeat(np.repeat(map_data, s, axis=0), s, axis=1).astype(np.uint8)
        # P6 ppm (rgb)
        ppm_header = f"P6\n{w*s} {h*s}\n255\n".encode("ascii")
        rgb = np.stack([big, big, big], axis=2).tobytes()
        self._photo = tk.PhotoImage(data=ppm_header + rgb, format="PPM")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        # วาดเส้น grid 0.5m
        for wx in self._frange(self.ox, self.ox + w * self.res, 0.5):
            cx, _ = self.world_to_canvas(wx, 0)
            self.canvas.create_line(cx, 0, cx, self.canvas_h, fill="#ddd", dash=(2, 4))
        for wy in self._frange(self.oy, self.oy + h * self.res, 0.5):
            _, cy = self.world_to_canvas(0, wy)
            self.canvas.create_line(0, cy, self.canvas_w, cy, fill="#ddd", dash=(2, 4))

    def _load_existing(self):
        # เสก waypoint เดิมจาก nav_waypoints.yaml ขึ้นมาให้ลากแก้ได้เลย
        if not os.path.exists(OUT_YAML):
            return
        try:
            with open(OUT_YAML) as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"  (โหลด {OUT_YAML} เดิมไม่ได้: {e})", flush=True)
            return
        wps = data.get("waypoints", []) or []
        for wp in wps:
            wtype = "HOME" if wp.get("task") == "HOME" else wp.get("type", "person")
            # วาด via ก่อน (ลำดับ artist เหมือนตอนวางจริง: via แล้วค่อย wp)
            for v in wp.get("via", []):
                vids = self._draw_arrow(v["x"], v["y"], self._pose_yaw(v), "orange")
                self.artists.append(("via", vids))
                self.markers.append({"kind": "via", "ids": vids, "pose": v})
            color = self.TYPE_COLORS.get(wtype, "red")
            ids = self._draw_arrow(wp["x"], wp["y"], self._pose_yaw(wp),
                                   color, label=wp.get("task"))
            self.artists.append(("wp", ids))
            self.markers.append({"kind": "wp", "ids": ids, "pose": wp})
            self.waypoints.append(wp)
        self._redraw_route()
        print(f"  ✎ โหลด waypoint เดิม {len(wps)} จุด จาก {OUT_YAML} — ลากแก้ได้เลย", flush=True)

    @staticmethod
    def _frange(a, b, step):
        v = math.ceil(a / step) * step
        while v <= b + 1e-9:
            yield v
            v += step

    # ---------- event handlers ----------
    def on_motion(self, event):
        wx, wy = self._snap(*self.canvas_to_world(event.x, event.y))
        cx, cy = self.world_to_canvas(wx, wy)   # ตำแหน่งหลัง snap (เล็งล็อกช่อง)
        # เส้นเล็งกากบาท + พิกัดลอยข้างเคอร์เซอร์
        self.canvas.coords(self.cross_v, cx, 0, cx, self.canvas_h)
        self.canvas.coords(self.cross_h, 0, cy, self.canvas_w, cy)
        self.canvas.coords(self.cursor_txt, cx + 10, cy - 6)
        self.canvas.itemconfig(self.cursor_txt, text=f"{wx:+.2f}, {wy:+.2f}")
        for cid in (self.cross_v, self.cross_h, self.cursor_txt):
            self.canvas.tag_raise(cid)
        # เส้นยางพรีวิวทิศ ตอนรอคลิก heading
        if self.pending is not None:
            cx1, cy1 = self.world_to_canvas(self.pending[1], self.pending[2])
            if self.rubber is None:
                self.rubber = self.canvas.create_line(cx1, cy1, cx, cy,
                                                      fill="#ff8c00", width=2, arrow="last")
            else:
                self.canvas.coords(self.rubber, cx1, cy1, cx, cy)
            self.canvas.tag_raise(self.rubber)
        elif self.rubber is not None:
            self.canvas.delete(self.rubber)
            self.rubber = None
        self.status.config(text=f"world: x={wx:+.3f}  y={wy:+.3f}   |  "
                                f"type ถัดไป=[{self.next_type}]  wp={len(self.waypoints)}  via buffer={len(self.via_buffer)}"
                                + (f"  | รอคลิก heading ของ {self.pending[0]}" if self.pending else ""))

    def on_click(self, event, button):
        # คลิกซ้ายค้างบนจุดที่วางแล้ว (และไม่ได้กำลังวางจุดใหม่) → เริ่มลากย้าย
        if button == 1 and self.pending is None:
            m = self._marker_at(event.x, event.y)
            if m is not None:
                self.dragging = m
                # Shift = หมุนทิศ (ตรึงตำแหน่ง), เปล่า = ย้ายตำแหน่ง
                self.drag_mode = "rotate" if (event.state & 0x0001) else "move"
                return
        wx, wy = self._snap(*self.canvas_to_world(event.x, event.y))
        scx, scy = self.world_to_canvas(wx, wy)   # ตำแหน่ง marker หลัง snap
        print(f"click button={button} canvas=({event.x},{event.y}) world=({wx:.3f},{wy:.3f})", flush=True)

        if self.pending is not None:
            kind, x1, y1 = self.pending
            yaw = math.atan2(wy - y1, wx - x1)
            pose = pose_dict(x1, y1, yaw)
            self.pending = None
            if self.rubber is not None:          # ลบเส้นยางพรีวิวทิศ
                self.canvas.delete(self.rubber)
                self.rubber = None
            if kind == "wp":
                self._finalize_waypoint(pose)
            else:
                self._finalize_via(pose)
            self._update_status()
            return

        if button == 1:
            self.pending = ("wp", wx, wy)
            r = 5
            ids = [self.canvas.create_oval(scx - r, scy - r, scx + r, scy + r,
                                           fill="red", outline="")]
            self.artists.append(("pending", ids))
        elif button == 3:
            self.pending = ("via", wx, wy)
            r = 5
            ids = [self.canvas.create_rectangle(scx - r, scy - r, scx + r, scy + r,
                                                fill="orange", outline="")]
            self.artists.append(("pending", ids))
        self._update_status()

    def on_drag(self, event):
        if self.dragging is None:
            return
        m = self.dragging
        if self.drag_mode == "rotate":
            # หมุนทิศ: ตรึงตำแหน่งเดิม, yaw = มุมจากจุดไปยังเคอร์เซอร์ (ไม่ snap มุม)
            wx, wy = self.canvas_to_world(event.x, event.y)
            mx, my = m["pose"]["x"], m["pose"]["y"]
            yaw = math.atan2(wy - my, wx - mx)
            z, w = yaw_to_quat(yaw)
            m["pose"]["orientation"] = {"z": round(z, 5), "w": round(w, 5)}
            self._reposition_arrow(m["ids"], mx, my, yaw)
            self.status.config(text=f"หมุน {m['kind']} → yaw={math.degrees(yaw):+.1f}°  (ตรึงตำแหน่ง)")
            return
        # ย้ายตำแหน่ง (คงทิศเดิม)
        wx, wy = self._snap(*self.canvas_to_world(event.x, event.y))
        m["pose"]["x"] = round(float(wx), 3)
        m["pose"]["y"] = round(float(wy), 3)
        self._reposition_arrow(m["ids"], wx, wy, self._pose_yaw(m["pose"]))
        self._redraw_route()
        self.status.config(text=f"ลาก {m['kind']} → x={wx:+.3f}  y={wy:+.3f}  (คงทิศเดิม)")

    def on_release(self, event):
        if self.dragging is None:
            return
        m = self.dragging
        self.dragging = None
        if self.drag_mode == "rotate":
            print(f"  ⟳ หมุน {m['kind']} → yaw={math.degrees(self._pose_yaw(m['pose'])):+.1f}°", flush=True)
        else:
            print(f"  ↔ ย้าย {m['kind']} → ({m['pose']['x']:.3f},{m['pose']['y']:.3f})", flush=True)
        self._update_status()

    def _draw_arrow(self, wx, wy, yaw, color, label=None):
        cx, cy = self.world_to_canvas(wx, wy)
        L_world = 0.20
        cx2, cy2 = self.world_to_canvas(wx + L_world * math.cos(yaw), wy + L_world * math.sin(yaw))
        ids = []
        r = 6
        ids.append(self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color, outline=""))
        ids.append(self.canvas.create_line(cx, cy, cx2, cy2, fill=color, width=2, arrow="last"))
        if label:
            ids.append(self.canvas.create_text(cx + 8, cy - 10, text=label,
                                               fill=color, font=("TkDefaultFont", 9, "bold")))
        return ids

    @staticmethod
    def _pose_yaw(pose):
        z, w = pose["orientation"]["z"], pose["orientation"]["w"]
        return math.atan2(2 * z * w, 1 - 2 * z ** 2)

    def _reposition_arrow(self, ids, wx, wy, yaw):
        # ขยับ artist เดิม (oval, line, [text]) ไปตำแหน่งใหม่ — ไม่สร้าง id ใหม่
        cx, cy = self.world_to_canvas(wx, wy)
        L_world = 0.20
        cx2, cy2 = self.world_to_canvas(wx + L_world * math.cos(yaw), wy + L_world * math.sin(yaw))
        r = 6
        self.canvas.coords(ids[0], cx - r, cy - r, cx + r, cy + r)
        self.canvas.coords(ids[1], cx, cy, cx2, cy2)
        if len(ids) >= 3:
            self.canvas.coords(ids[2], cx + 8, cy - 10)
        for cid in ids:
            self.canvas.tag_raise(cid)

    def _redraw_route(self):
        # วาดเส้นเชื่อมตามลำดับเดิน: ในแต่ละ wp เดินผ่าน via ก่อนแล้วถึงตัว wp,
        # ต่อด้วย via_buffer ที่ยังค้าง (จะผูกกับ wp ถัดไป)
        for cid in self.route_ids:
            self.canvas.delete(cid)
        self.route_ids = []

        def seg(p1, p2, color):
            x1, y1 = self.world_to_canvas(*p1)
            x2, y2 = self.world_to_canvas(*p2)
            self.route_ids.append(
                self.canvas.create_line(x1, y1, x2, y2, fill=color, width=2, dash=(6, 3)))

        # สีเส้น = สีของ waypoint ปลายทางของช่วงนั้น (อ่านง่ายแบบ draw_waypoints.py)
        prev = None
        for wp in self.waypoints:
            wtype = "HOME" if wp.get("task") == "HOME" else wp.get("type", "person")
            color = self.TYPE_COLORS.get(wtype, "green")
            leg = ([prev] if prev is not None else []) \
                + [(v["x"], v["y"]) for v in wp.get("via", [])] \
                + [(wp["x"], wp["y"])]
            for i in range(len(leg) - 1):
                seg(leg[i], leg[i + 1], color)
            prev = (wp["x"], wp["y"])
        # via ที่ยังค้าง buffer (จะผูกกับ wp ถัดไป) — สีเทา
        if self.via_buffer:
            leg = ([prev] if prev is not None else []) \
                + [(v["x"], v["y"]) for v in self.via_buffer]
            for i in range(len(leg) - 1):
                seg(leg[i], leg[i + 1], "#888")
        # ให้เส้นอยู่ใต้ marker/ลูกศร (แต่เหนือแผนที่): ดัน marker + เส้นเล็งขึ้นทับ
        for m in self.markers:
            for cid in m["ids"]:
                self.canvas.tag_raise(cid)
        for cid in (self.cross_v, self.cross_h, self.cursor_txt):
            self.canvas.tag_raise(cid)
        if self.rubber is not None:
            self.canvas.tag_raise(self.rubber)

    def _marker_at(self, cx, cy):
        # หา marker ที่จุด dot อยู่ใกล้ (cx,cy) ที่สุด ภายในรัศมีจับ
        hit_r = max(10, self.scale)
        best, best_d = None, hit_r
        for m in self.markers:
            mcx, mcy = self.world_to_canvas(m["pose"]["x"], m["pose"]["y"])
            d = math.hypot(cx - mcx, cy - mcy)
            if d <= best_d:
                best, best_d = m, d
        return best

    def _drop_marker(self, ids):
        self.markers = [m for m in self.markers if m["ids"] is not ids]

    def _finalize_waypoint(self, pose):
        # ลบ marker pending
        if self.artists and self.artists[-1][0] == "pending":
            for cid in self.artists.pop()[1]:
                self.canvas.delete(cid)

        is_home = self.next_type == "HOME"
        task = "HOME" if is_home else f"waypoint_{sum(1 for w in self.waypoints if w['task'] != 'HOME') + 1}"
        wp = {"task": task, "x": pose["x"], "y": pose["y"], "orientation": pose["orientation"]}
        if not is_home:
            wp["type"] = self.next_type
        if self.via_buffer:
            wp["via"] = self.via_buffer[:]
            self.via_buffer = []
        self.waypoints.append(wp)

        yaw = math.atan2(2 * pose["orientation"]["z"] * pose["orientation"]["w"],
                         1 - 2 * pose["orientation"]["z"] ** 2)
        color = self.TYPE_COLORS[self.next_type]
        ids = self._draw_arrow(pose["x"], pose["y"], yaw, color, label=task)
        self.artists.append(("wp", ids))
        self.markers.append({"kind": "wp", "ids": ids, "pose": wp})
        self._redraw_route()
        print(f"  + {task} ({self.next_type}) ({pose['x']:.3f},{pose['y']:.3f}) yaw={math.degrees(yaw):.1f}°"
              + (f" +{len(wp.get('via', []))} via" if "via" in wp else ""), flush=True)

    def _finalize_via(self, pose):
        if self.artists and self.artists[-1][0] == "pending":
            for cid in self.artists.pop()[1]:
                self.canvas.delete(cid)
        self.via_buffer.append(pose)
        yaw = math.atan2(2 * pose["orientation"]["z"] * pose["orientation"]["w"],
                         1 - 2 * pose["orientation"]["z"] ** 2)
        ids = self._draw_arrow(pose["x"], pose["y"], yaw, "orange")
        self.artists.append(("via", ids))
        self.markers.append({"kind": "via", "ids": ids, "pose": pose})
        self._redraw_route()
        print(f"  · via ({pose['x']:.3f},{pose['y']:.3f}) yaw={math.degrees(yaw):.1f}°  buf={len(self.via_buffer)}",
              flush=True)

    # ---------- actions ----------
    def undo(self):
        if not self.artists:
            return
        kind, ids = self.artists.pop()
        for cid in ids:
            self.canvas.delete(cid)
        self._drop_marker(ids)
        if kind == "wp":
            removed = self.waypoints.pop()
            if "via" in removed:
                self.via_buffer = removed["via"] + self.via_buffer
            print(f"  - undo {removed['task']}", flush=True)
        elif kind == "via":
            if self.via_buffer:
                self.via_buffer.pop()
            print("  - undo via", flush=True)
        elif kind == "pending":
            self.pending = None
        self._redraw_route()
        self._update_status()

    def clear_via(self):
        # ลบทั้ง via_buffer + via artist ทั้งหมดที่ยังไม่ผูก wp
        # ง่ายสุด: เคลียร์ buffer ก่อน แล้ว artist via ที่อยู่ท้ายสุด (ก่อนจะมี wp ถัดไป) ก็ลบทิ้งหน้าจอ
        self.via_buffer = []
        # ลบ via artist ทั้งหมดท้าย stack จนกว่าจะเจอ wp
        while self.artists and self.artists[-1][0] == "via":
            ids = self.artists.pop()[1]
            for cid in ids:
                self.canvas.delete(cid)
            self._drop_marker(ids)
        print("  (เคลียร์ via buffer)", flush=True)
        self._redraw_route()
        self._update_status()

    def save(self):
        if not self.waypoints:
            messagebox.showinfo("Save", "ยังไม่มี waypoint, ข้ามการเซฟ")
            return False
        if os.path.exists(OUT_YAML):
            shutil.copyfile(OUT_YAML, OUT_YAML + ".bak")
        with open(OUT_YAML, "w") as f:
            yaml.safe_dump({"waypoints": self.waypoints}, f, sort_keys=False, allow_unicode=True)
        msg = f"เซฟ {len(self.waypoints)} waypoint(s) → {OUT_YAML}"
        if os.path.exists(OUT_YAML + ".bak"):
            msg += "\n(backup: nav_waypoints.yaml.bak)"
        print("  ✓ " + msg.replace("\n", " "), flush=True)
        messagebox.showinfo("Save", msg)
        return True

    def save_and_quit(self):
        if self.save() or not self.waypoints:
            self.root.quit()

    def _update_status(self):
        self.status.config(text=f"type ถัดไป=[{self.next_type}]  wp={len(self.waypoints)}  via buffer={len(self.via_buffer)}"
                                + (f"  | รอคลิก heading ของ {self.pending[0]}" if self.pending else ""))


def main():
    if not os.path.exists(MAP_YAML):
        print(f"ไม่พบ {MAP_YAML} — ต้องรันจาก navigator_map/", file=sys.stderr)
        sys.exit(1)
    data, res, origin, (w, h) = load_map(MAP_YAML)
    print(f"แผนที่ {w}x{h} px  res={res} m  origin={origin}", flush=True)
    print(f"world extent: x=[{origin[0]:.2f}, {origin[0]+w*res:.2f}]  "
          f"y=[{origin[1]:.2f}, {origin[1]+h*res:.2f}]", flush=True)

    root = tk.Tk()
    app = Picker(root, data, res, origin, (w, h))
    root.mainloop()


if __name__ == "__main__":
    main()

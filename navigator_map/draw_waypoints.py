#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""วาด waypoint ปัจจุบันจาก nav_waypoints.yaml ทับบนแผนที่ my_robot_map.pgm
ผลลัพธ์: docs/wp_overlay.png
"""
import math
import yaml
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import sys
MAP_PGM = "my_robot_map.pgm"
MAP_YAML = "my_robot_map.yaml"
WP_YAML = sys.argv[1] if len(sys.argv) > 1 else "nav_waypoints.yaml"
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/wp_overlay.png"

# โหลด map
with open(MAP_YAML) as f:
    minfo = yaml.safe_load(f)
res = minfo["resolution"]
ox, oy = minfo["origin"][0], minfo["origin"][1]
img = np.array(Image.open(MAP_PGM))
h, w = img.shape

# world extent (ภาพ pgm แถวบน = y สูงสุด)
xmin, xmax = ox, ox + w * res
ymin, ymax = oy, oy + h * res

# โหลด waypoints
with open(WP_YAML) as f:
    wps = yaml.safe_load(f)["waypoints"]

fig, ax = plt.subplots(figsize=(9, 8))
ax.imshow(img, cmap="gray", origin="upper",
          extent=[xmin, xmax, ymin, ymax], zorder=0)

def yaw_from_quat(z, w):
    return math.atan2(2.0 * w * z, 1.0 - 2.0 * z * z)

colors = {"tag": "tab:blue", "person": "tab:red", None: "tab:green"}

prev = None
for i, wp in enumerate(wps):
    typ = wp.get("type")
    x, y = wp["x"], wp["y"]
    c = colors.get(typ, "tab:green")

    # via points + เส้นเชื่อม
    pts = []
    if prev is not None:
        pts.append(prev)
    for v in wp.get("via", []):
        pts.append((v["x"], v["y"]))
        ax.plot(v["x"], v["y"], "x", color="gray", ms=8, mew=2, zorder=3)
        if "orientation" in v:   # ลูกศรทิศของ via
            vyaw = yaw_from_quat(v["orientation"]["z"], v["orientation"]["w"])
            ax.arrow(v["x"], v["y"], 0.16 * math.cos(vyaw), 0.16 * math.sin(vyaw),
                     head_width=0.05, head_length=0.05, fc="gray", ec="gray", zorder=4)
    pts.append((x, y))
    px = [p[0] for p in pts]
    py = [p[1] for p in pts]
    ax.plot(px, py, "--", color=c, lw=1.2, alpha=0.7, zorder=2)

    # จุด waypoint
    ax.plot(x, y, "o", color=c, ms=14, zorder=5,
            markeredgecolor="black", markeredgewidth=1.2)
    # ลูกศรทิศทาง (orientation)
    yaw = yaw_from_quat(wp["orientation"]["z"], wp["orientation"]["w"])
    ax.arrow(x, y, 0.22 * math.cos(yaw), 0.22 * math.sin(yaw),
             head_width=0.07, head_length=0.07, fc=c, ec=c, zorder=6)

    label = wp["task"] + (f"\n({typ})" if typ else "")
    ax.annotate(label, (x, y), textcoords="offset points",
                xytext=(10, 8), fontsize=9, fontweight="bold",
                color=c, zorder=7)
    prev = (x, y)

# legend
from matplotlib.lines import Line2D
legend = [
    Line2D([0], [0], marker="o", color="w", markerfacecolor="tab:blue", ms=11, label="tag"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="tab:red", ms=11, label="person"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor="tab:green", ms=11, label="HOME"),
    Line2D([0], [0], marker="x", color="gray", ms=9, mew=2, ls="", label="via"),
]
ax.legend(handles=legend, loc="upper right", fontsize=9)

ax.set_title("Current waypoints (nav_waypoints.yaml) over map", fontsize=12)
ax.set_xlabel("x (m)")
ax.set_ylabel("y (m)")
ax.set_xlim(xmin, xmax)
ax.set_ylim(ymin, ymax)
ax.grid(True, alpha=0.2)
plt.tight_layout()
plt.savefig(OUT, dpi=130)
print(f"saved -> {OUT}  ({w}x{h}px, extent X[{xmin:.2f},{xmax:.2f}] Y[{ymin:.2f},{ymax:.2f}])")

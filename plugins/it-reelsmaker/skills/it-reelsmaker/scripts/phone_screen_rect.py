# -*- coding: utf-8 -*-
"""The screen rectangle inside a phone frame PNG (a phone mockup whose screen is transparent).

The screen in the frame is a transparent area around the center of the image. The script finds its edges and the
corner radius, so that a screen recording can be placed exactly under the frame.

    python scripts/phone_screen_rect.py "<frame.png>" [width_in_video_px]

Prints JSON: the frame size, the screen rectangle (x, y, w, h) and the radius in source pixels, and, if the frame's
width in the video is given, the same values scaled to it. Needs Pillow.
"""
import json, sys

if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    print(__doc__)
    sys.exit(0 if len(sys.argv) > 1 else 2)

from PIL import Image

p = sys.argv[1]
target_w = int(sys.argv[2]) if len(sys.argv) > 2 else None
im = Image.open(p).convert("RGBA")
W, H = im.size
a = im.getchannel("A").load()
cx, cy = W // 2, H // 2
if a[cx, cy] > 10:
    sys.exit("the center of the frame is not transparent: this is not a frame with an empty screen")


def run(x, y, dx, dy):
    while 0 <= x + dx < W and 0 <= y + dy < H and a[x + dx, y + dy] <= 10:
        x, y = x + dx, y + dy
    return x, y


left = run(cx, cy, -1, 0)[0]
right = run(cx, cy, 1, 0)[0]
# top/bottom are searched a quarter of the screen width from its edge: in the center the notch (camera cutout) gets in the way
qx = left + (right - left) // 4
top = run(qx, cy, 0, -1)[1]
bottom = run(qx, cy, 0, 1)[1]
# radius: how far inward along the diagonal from the screen corner the transparency starts
k = 0
while left + k < right and a[left + k, top + k] > 10:
    k += 1
radius = round(k / 0.2929) if k else 0  # for a circular arc: the diagonal offset = r·(1−1/√2)
res = {"frame": [W, H], "screen": {"x": left, "y": top, "w": right - left + 1, "h": bottom - top + 1},
       "radius": radius}
if target_w:
    s = target_w / W
    res["scaled_to_width"] = target_w
    res["screen_scaled"] = {k2: round(v * s) for k2, v in res["screen"].items()}
    res["radius_scaled"] = round(radius * s)
print(json.dumps(res, ensure_ascii=False))

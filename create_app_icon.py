#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'assets' / 'icons'
OUT.mkdir(parents=True, exist_ok=True)

SIZE = 1024
img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# --- background ---
# dark navy -> electric blue gradient for a premium utility look
for y in range(SIZE):
    t = y / (SIZE - 1)
    r = int(18 + (40 - 18) * t)
    g = int(30 + (84 - 30) * t)
    b = int(58 + (175 - 58) * t)
    d.line((0, y, SIZE, y), fill=(r, g, b, 255))

# subtle vignette
vignette = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
vd = ImageDraw.Draw(vignette)
for i in range(18):
    alpha = int(10 + i * 3)
    margin = i * 8
    vd.rounded_rectangle((margin, margin, SIZE-margin, SIZE-margin), radius=220, outline=(0,0,0,alpha), width=12)
img = Image.alpha_composite(img, vignette)
d = ImageDraw.Draw(img)

# glossy light glow top-right
glow = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
gd.ellipse((520, -40, 1080, 520), fill=(255, 255, 255, 48))
glow = glow.filter(ImageFilter.GaussianBlur(70))
img = Image.alpha_composite(img, glow)
d = ImageDraw.Draw(img)

# rounded base card shadow
shadow = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle((120, 150, 910, 850), radius=150, fill=(0, 0, 0, 100))
shadow = shadow.filter(ImageFilter.GaussianBlur(35))
img = Image.alpha_composite(img, shadow)
d = ImageDraw.Draw(img)

# --- main folder body ---
folder_back = (145, 183, 255, 255)
folder_front = (237, 244, 255, 255)
folder_edge = (94, 126, 214, 255)

# top tab
left, top, right, bottom = 150, 220, 890, 820

d.rounded_rectangle((210, 170, 520, 310), radius=55, fill=(202, 220, 255, 255))
d.rounded_rectangle((left, 250, right, bottom), radius=120, fill=folder_back)
d.rounded_rectangle((left, 250, right, bottom), radius=120, outline=folder_edge, width=8)

# front folder flap
flap = [(170, 360), (385, 360), (470, 305), (870, 305), (870, 790), (170, 790)]
d.polygon(flap, fill=folder_front)
d.line(flap + [flap[0]], fill=folder_edge, width=8)

# --- inner media card ---
card_shadow = Image.new('RGBA', (SIZE, SIZE), (0,0,0,0))
cs = ImageDraw.Draw(card_shadow)
cs.rounded_rectangle((255, 385, 770, 735), radius=70, fill=(0,0,0,110))
card_shadow = card_shadow.filter(ImageFilter.GaussianBlur(22))
img = Image.alpha_composite(img, card_shadow)
d = ImageDraw.Draw(img)

d.rounded_rectangle((235, 365, 750, 715), radius=70, fill=(255,255,255,255))
d.rounded_rectangle((235, 365, 750, 715), radius=70, outline=(197, 210, 232, 255), width=5)

# media thumbnail area with warm poster gradient
poster = Image.new('RGBA', (SIZE, SIZE), (0,0,0,0))
pd = ImageDraw.Draw(poster)
px1, py1, px2, py2 = 275, 405, 555, 675
for y in range(py1, py2):
    t = (y - py1) / (py2 - py1)
    r = int(238 + (194 - 238) * t)
    g = int(94 + (56 - 94) * t)
    b = int(98 + (78 - 98) * t)
    pd.line((px1, y, px2, y), fill=(r, g, b, 255))
# subtle play triangle highlight
pd.polygon([(365, 475), (365, 605), (475, 540)], fill=(255,255,255,180))
poster = poster.filter(ImageFilter.GaussianBlur(0.3))
img = Image.alpha_composite(img, poster)
d = ImageDraw.Draw(img)
d.rounded_rectangle((px1, py1, px2, py2), radius=40, outline=(255,255,255,90), width=4)

# metadata lines on right side
line_color = (149, 168, 214, 255)
for i, w in enumerate([145, 120, 160, 100]):
    y = 440 + i * 58
    d.rounded_rectangle((600, y, 600 + w, y + 18), radius=9, fill=line_color)

# film perforations around poster to imply video library
for y in range(430, 661, 46):
    d.rounded_rectangle((250, y, 266, y + 22), radius=5, fill=(255,255,255,165))
    d.rounded_rectangle((564, y, 580, y + 22), radius=5, fill=(255,255,255,165))

# --- downloading badge ---
# floating badge bottom-right: indicates downloading/importing into organized folder
badge_shadow = Image.new('RGBA', (SIZE, SIZE), (0,0,0,0))
bsd = ImageDraw.Draw(badge_shadow)
bsd.ellipse((640, 625, 900, 885), fill=(0,0,0,120))
badge_shadow = badge_shadow.filter(ImageFilter.GaussianBlur(18))
img = Image.alpha_composite(img, badge_shadow)
d = ImageDraw.Draw(img)

d.ellipse((625, 610, 885, 870), fill=(34, 198, 124, 255), outline=(255,255,255,180), width=8)
# tray
tray_y = 768
d.rounded_rectangle((692, tray_y, 818, tray_y + 28), radius=14, fill=(255,255,255,255))
# downward shaft
d.rounded_rectangle((741, 668, 769, 760), radius=14, fill=(255,255,255,255))
# arrow head
d.polygon([(708, 734), (802, 734), (755, 792)], fill=(255,255,255,255))

# sparkle = cleanup / smart automation
for cx, cy, s in [(760, 225, 18), (810, 185, 12), (705, 210, 10)]:
    d.line((cx - s, cy, cx + s, cy), fill=(255, 232, 126, 255), width=7)
    d.line((cx, cy - s, cx, cy + s), fill=(255, 232, 126, 255), width=7)

# rounded mask to make icon-app style corners
mask = Image.new('L', (SIZE, SIZE), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle((0, 0, SIZE, SIZE), radius=220, fill=255)
img.putalpha(mask)

png_path = OUT / 'app_icon_1024.png'
img.save(png_path)
print(png_path)

# iconset sizes for macOS icns
iconset = OUT / 'JAVFileOrganizer.iconset'
iconset.mkdir(exist_ok=True)
for size in [16, 32, 128, 256, 512]:
    for scale in [1, 2]:
        px = size * scale
        resized = img.resize((px, px), Image.Resampling.LANCZOS)
        name = f'icon_{size}x{size}' + ('@2x' if scale == 2 else '') + '.png'
        resized.save(iconset / name)
print(iconset)

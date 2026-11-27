from PIL import Image, ImageDraw, ImageFilter
import math
import os

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# Rounded glass plate with a cold blue vertical wash.
plate = Image.new("RGBA", (S, S), (0, 0, 0, 0))
pd = ImageDraw.Draw(plate)
for y in range(S):
    t = y / (S - 1)
    r = int(5 + 10 * t)
    g = int(12 + 14 * t)
    b = int(26 + 26 * t)
    pd.line([(0, y), (S, y)], fill=(r, g, b, 255))
mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([34, 34, S - 34, S - 34], radius=220, fill=255)
img.paste(plate, (0, 0), mask)

# Soft cyan glow.
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
for i in range(10, 0, -1):
    radius = 250 + i * 24
    alpha = int(4 * (11 - i))
    gd.ellipse([S/2 - radius, S/2 - radius, S/2 + radius, S/2 + radius], fill=(69, 190, 255, alpha))
glow = glow.filter(ImageFilter.GaussianBlur(24))
img = Image.alpha_composite(img, glow)

# Gear mask: central disc plus 10 rounded teeth, then a dark hub and a cyan bore.
cx = cy = S / 2
gear = Image.new("L", (S, S), 0)
gd = ImageDraw.Draw(gear)
gd.ellipse([cx - 285, cy - 285, cx + 285, cy + 285], fill=255)
for i in range(10):
    angle = i * 36
    tooth = Image.new("L", (S, S), 0)
    td = ImageDraw.Draw(tooth)
    td.rounded_rectangle([cx - 58, cy - 372, cx + 58, cy - 245], radius=40, fill=255)
    tooth = tooth.rotate(angle, resample=Image.BICUBIC, center=(cx, cy))
    gear = Image.composite(Image.new("L", (S, S), 255), gear, tooth)
# Inner cutout.
gd = ImageDraw.Draw(gear)
gd.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill=0)

# Blue gradient fill for gear.
blue = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bd = ImageDraw.Draw(blue)
for y in range(S):
    t = y / (S - 1)
    r = int(90 + 28 * t)
    g = int(210 + 26 * t)
    b = int(255 - 12 * t)
    bd.line([(0, y), (S, y)], fill=(r, g, b, 255))
img.paste(blue, (0, 0), gear)

# Inner shadow ring and center jewel.
layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ld = ImageDraw.Draw(layer)
ld.ellipse([cx - 148, cy - 148, cx + 148, cy + 148], fill=(8, 18, 34, 255))
ld.ellipse([cx - 122, cy - 122, cx + 122, cy + 122], fill=(16, 52, 88, 255))
ld.ellipse([cx - 54, cy - 54, cx + 54, cy + 54], fill=(212, 244, 255, 255))
ld.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=(8, 26, 46, 255))
img = Image.alpha_composite(img, layer)

# Rim highlight.
rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
rd = ImageDraw.Draw(rim)
rd.rounded_rectangle([34, 34, S - 34, S - 34], radius=220, outline=(190, 235, 255, 45), width=3)
img = Image.alpha_composite(img, rim)

assets = os.path.join(os.path.dirname(__file__), "..", "assets")
os.makedirs(assets, exist_ok=True)
sizes = [256, 128, 64, 48, 32, 24, 16]
frames = [img.resize((s, s), Image.LANCZOS) for s in sizes]
frames[0].save(os.path.join(assets, "DiskManager.ico"), format="ICO", sizes=[(s, s) for s in sizes])
frames[0].save(os.path.join(assets, "DiskManager.png"), format="PNG")
print("icon written", os.path.join(assets, "DiskManager.ico"))

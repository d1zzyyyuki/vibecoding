"""Generate the HLTV-AdBlocker extension icons."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extension" / "icons"


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_master() -> Image.Image:
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 冷蓝底，和项目 02 的冷色蓝主题保持一致
    rounded_rect(d, (20, 20, size - 20, size - 20), 112, (23, 105, 224, 255))
    rounded_rect(d, (40, 40, size - 40, size - 40), 96, (10, 43, 94, 255))

    # 盾牌
    shield = [
        (256, 82),
        (402, 138),
        (402, 264),
        (256, 430),
        (110, 264),
        (110, 138),
    ]
    d.polygon(shield, fill=(245, 249, 255, 255), outline=(255, 255, 255, 255))
    d.polygon(
        [
            (256, 108),
            (378, 154),
            (378, 258),
            (256, 396),
            (134, 258),
            (134, 154),
        ],
        fill=(23, 105, 224, 255),
    )

    # 禁止斜杠
    d.line([(160, 356), (352, 164)], fill=(255, 100, 100, 255), width=42)
    d.line([(160, 164), (352, 356)], fill=(255, 100, 100, 255), width=42)

    # 中心 AD 字样
    font = None
    for candidate in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ):
        try:
            font = ImageFont.truetype(candidate, 146)
            break
        except OSError:
            font = None
    if font is not None:
        d.text((256, 260), "AD", anchor="mm", fill=(255, 255, 255, 255), font=font)
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "assets").mkdir(parents=True, exist_ok=True)
    master = make_master()
    for size in (16, 32, 48, 128):
        icon = master.resize((size, size), Image.Resampling.LANCZOS)
        icon.save(OUT / f"icon{size}.png")
    master.save(ROOT / "assets" / "icon-master.png")


if __name__ == "__main__":
    main()

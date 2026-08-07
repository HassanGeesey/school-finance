"""Generate the School Finance app icon (tray image + exe icon).

Run once with the build environment's Python::

    python packaging/generate_icon.py

Writes ``icon.png`` (256px, used by the tray) and ``icon.ico`` (multi-size,
used as the .exe icon) into this folder. The design is a teal rounded square
matching the ``schoolfinance`` theme primary colour (#0d9488) with a white
banknote-and-coin mark.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

PRIMARY = (13, 148, 136, 255)
WHITE = (255, 255, 255, 255)
HERE = Path(__file__).resolve().parent


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(4, int(size * 0.22))
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=PRIMARY)

    # The note: a white rounded rectangle sitting slightly above centre.
    nw = int(size * 0.55)
    nh = int(size * 0.36)
    left = (size - nw) // 2
    top = int(size * 0.26)
    draw.rounded_rectangle(
        (left, top, left + nw - 1, top + nh - 1), radius=int(size * 0.05), fill=WHITE
    )

    # The coin: a primary circle centred on the note.
    coin = int(size * 0.16)
    cx, cy = size // 2, top + nh // 2
    draw.ellipse((cx - coin, cy - coin, cx + coin, cy + coin), fill=PRIMARY)

    # A ring inside the note ties the two shapes together.
    ring = int(size * 0.26)
    draw.ellipse(
        (cx - ring, cy - ring, cx + ring, cy + ring), outline=PRIMARY, width=max(1, int(size * 0.03))
    )
    return img


def main() -> None:
    icon = draw_icon(256)
    icon.save(HERE / "icon.png")
    icon.save(
        HERE / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Wrote {HERE / 'icon.png'} and {HERE / 'icon.ico'}")


if __name__ == "__main__":
    main()

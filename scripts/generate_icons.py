#!/usr/bin/env python3
"""Generate cohesive SDNUI brand icons across web (SVG/ICO/PNG), JavaFX UI, and Windows packaging.

Uses supersampled rendering (1024x1024 -> LANCZOS) with Pillow so raster assets match
site/assets/favicon.svg faithfully across 16x16 favicons through 512x512 app icons.
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parent.parent
SITE_ASSETS = REPO / "site" / "assets"
UI_ICONS = REPO / "ui" / "src" / "main" / "resources" / "sdfx" / "ui" / "icons"

SVG_CONTENT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="8" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#11182c"/>
      <stop offset="0.52" stop-color="#1d4ed8"/>
      <stop offset="1" stop-color="#0ea5e9"/>
    </linearGradient>
    <radialGradient id="glow" cx="50%" cy="48%" r="48%">
      <stop offset="0" stop-color="#7dd3fc" stop-opacity="0.45"/>
      <stop offset="0.55" stop-color="#38bdf8" stop-opacity="0.14"/>
      <stop offset="1" stop-color="#0ea5e9" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="rim" x1="10" y1="6" x2="54" y2="58" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.34"/>
      <stop offset="0.45" stop-color="#93c5fd" stop-opacity="0.14"/>
      <stop offset="1" stop-color="#38bdf8" stop-opacity="0.06"/>
    </linearGradient>
    <linearGradient id="diamond" x1="16" y1="14" x2="48" y2="50" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#e0f2fe" stop-opacity="0.88"/>
      <stop offset="1" stop-color="#bae6fd" stop-opacity="0.45"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="14" fill="url(#bg)"/>
  <circle cx="32" cy="31" r="22" fill="url(#glow)"/>
  <rect x="5" y="5" width="54" height="54" rx="13" fill="none" stroke="url(#rim)" stroke-width="1.6"/>
  <rect x="15.5" y="15.5" width="33" height="33" rx="6.5" transform="rotate(45 32 32)" fill="none" stroke="url(#diamond)" stroke-width="2.2"/>
  <path d="M32 16 C33.9 26.2 37.8 30.1 48 32 C37.8 33.9 33.9 37.8 32 48 C30.1 37.8 26.2 33.9 16 32 C26.2 30.1 30.1 26.2 32 16 Z" fill="#ffffff"/>
  <circle cx="47.5" cy="16.5" r="2.3" fill="#e0f2fe"/>
  <circle cx="16.5" cy="47.5" r="1.8" fill="#bae6fd" fill-opacity="0.9"/>
</svg>
"""


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_rgb(c0: tuple[int, int, int], c1: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(round(_lerp(c0[0], c1[0], t))),
        int(round(_lerp(c0[1], c1[1], t))),
        int(round(_lerp(c0[2], c1[2], t))),
    )


def _rounded_rect_mask(size: int, pad: float, radius: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([pad, pad, size - 1 - pad, size - 1 - pad], radius=radius, fill=255)
    return mask


def _four_point_spark_polygon(cx: float, cy: float, outer_r: float, inner_r: float, steps: int = 24) -> list[tuple[float, float]]:
    """Build a crisp concave 4-point star polygon matching SVG cubic curves."""
    # Vertices go clockwise: Top -> InnerTR -> Right -> InnerBR -> Bottom -> InnerBL -> Left -> InnerTL
    pts: list[tuple[float, float]] = []
    anchors = [
        ((0.0, -outer_r), (outer_r * 0.12, -outer_r * 0.35), (outer_r * 0.35, -outer_r * 0.12), (outer_r, 0.0)),
        ((outer_r, 0.0), (outer_r * 0.35, outer_r * 0.12), (outer_r * 0.12, outer_r * 0.35), (0.0, outer_r)),
        ((0.0, outer_r), (-outer_r * 0.12, outer_r * 0.35), (-outer_r * 0.35, outer_r * 0.12), (-outer_r, 0.0)),
        ((-outer_r, 0.0), (-outer_r * 0.35, -outer_r * 0.12), (-outer_r * 0.12, -outer_r * 0.35), (0.0, -outer_r)),
    ]
    for p0, c1, c2, p3 in anchors:
        for i in range(steps):
            t = i / steps
            mt = 1.0 - t
            x = (mt**3) * p0[0] + 3 * (mt**2) * t * c1[0] + 3 * mt * (t**2) * c2[0] + (t**3) * p3[0]
            y = (mt**3) * p0[1] + 3 * (mt**2) * t * c1[1] + 3 * mt * (t**2) * c2[1] + (t**3) * p3[1]
            pts.append((cx + x, cy + y))
    return pts


def _draw_rotated_rounded_diamond(
    layer: Image.Image,
    cx: float,
    cy: float,
    side: float,
    corner_r: float,
    stroke_width: float,
    stroke_rgba: tuple[int, int, int, int],
) -> None:
    """Draw a 45-degree rotated rounded square ring onto an RGBA layer."""
    s = layer.size[0]
    tmp = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    half = side / 2.0
    d.rounded_rectangle(
        [cx - half, cy - half, cx + half, cy + half],
        radius=corner_r,
        fill=None,
        outline=stroke_rgba,
        width=max(1, int(round(stroke_width))),
    )
    rotated = tmp.rotate(45, resample=Image.Resampling.BICUBIC, center=(cx, cy))
    layer.alpha_composite(rotated)


def render_master(size: int = 1024, simplify_small: bool = False) -> Image.Image:
    """Render high-res RGBA icon.

    When simplify_small is True (for <= 24px sizes), strokes and star arms are slightly
    thicker and corner margin slightly tighter so small favicons stay bold and legible.
    """
    pad = size * (0.045 if simplify_small else 0.0625)
    radius = size * 0.22
    c0 = (17, 24, 44)      # #11182c deep midnight indigo
    c1 = (29, 78, 216)     # #1d4ed8 Fluent sapphire blue
    c2 = (14, 165, 233)    # #0ea5e9 sky cyan

    # Build diagonal gradient in small grid and upscale bilinearly for speed + smoothness
    grid_n = 256
    grad = Image.new("RGBA", (grid_n, grid_n), (0, 0, 0, 255))
    px = grad.load()
    denom = float(2 * (grid_n - 1))
    for y in range(grid_n):
        for x in range(grid_n):
            t = (x + y) / denom
            if t < 0.52:
                rgb = _lerp_rgb(c0, c1, t / 0.52)
            else:
                rgb = _lerp_rgb(c1, c2, (t - 0.52) / 0.48)
            px[x, y] = (rgb[0], rgb[1], rgb[2], 255)
    bg_full = grad.resize((size, size), Image.Resampling.BILINEAR)

    # Apply rounded squircle mask
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    squircle_mask = _rounded_rect_mask(size, pad, radius)
    canvas.paste(bg_full, (0, 0), squircle_mask)

    # Soft central cyan radial glow clipped to squircle
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx = cy = size / 2.0
    r_glow = size * 0.32
    gd.ellipse([cx - r_glow, cy - r_glow, cx + r_glow, cy + r_glow], fill=(125, 211, 252, 95))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=size * 0.11))
    clipped_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    clipped_glow.paste(glow, (0, 0), squircle_mask)
    canvas.alpha_composite(clipped_glow)

    # Subtle top-left specular inner rim
    rim_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim_layer)
    rim_inset = pad + size * 0.015
    rim_w = max(2, int(round(size * 0.025)))
    rd.rounded_rectangle(
        [rim_inset, rim_inset, size - 1 - rim_inset, size - 1 - rim_inset],
        radius=radius * 0.93,
        outline=(224, 242, 254, 72),
        width=rim_w,
    )
    canvas.alpha_composite(rim_layer)

    # Rotated diamond aperture frame (well-separated from center spark)
    diamond_side = size * (0.515 if simplify_small else 0.515)
    diamond_stroke = size * (0.044 if simplify_small else 0.034)
    _draw_rotated_rounded_diamond(
        canvas,
        cx,
        cy,
        side=diamond_side,
        corner_r=size * 0.10,
        stroke_width=diamond_stroke,
        stroke_rgba=(224, 242, 254, 190 if simplify_small else 175),
    )

    # Soft halo behind central spark
    spark_outer = size * (0.275 if simplify_small else 0.255)
    spark_pts = _four_point_spark_polygon(cx, cy, outer_r=spark_outer, inner_r=spark_outer * 0.2)
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.polygon(spark_pts, fill=(125, 211, 252, 130))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=size * 0.032))
    canvas.alpha_composite(halo)

    # Crisp white 4-point diffusion spark
    fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fg)
    fd.polygon(spark_pts, fill=(255, 255, 255, 255))

    if not simplify_small:
        # Two crisp satellite dots (top-right and bottom-left)
        dot1_x, dot1_y, dot1_r = size * 0.742, size * 0.258, size * 0.036
        fd.ellipse([dot1_x - dot1_r, dot1_y - dot1_r, dot1_x + dot1_r, dot1_y + dot1_r], fill=(224, 242, 254, 245))
        dot2_x, dot2_y, dot2_r = size * 0.258, size * 0.742, size * 0.028
        fd.ellipse([dot2_x - dot2_r, dot2_y - dot2_r, dot2_x + dot2_r, dot2_y + dot2_r], fill=(186, 230, 253, 225))
    else:
        dot1_x, dot1_y, dot1_r = size * 0.75, size * 0.25, size * 0.042
        fd.ellipse([dot1_x - dot1_r, dot1_y - dot1_r, dot1_x + dot1_r, dot1_y + dot1_r], fill=(224, 242, 254, 245))

    canvas.alpha_composite(fg)
    return canvas


def main() -> None:
    SITE_ASSETS.mkdir(parents=True, exist_ok=True)
    UI_ICONS.mkdir(parents=True, exist_ok=True)

    # 1. Vector SVG (LF line endings)
    (SITE_ASSETS / "favicon.svg").write_text(SVG_CONTENT.rstrip() + "\n", encoding="utf-8", newline="\n")

    # 2. High-res master renders
    master_std = render_master(1024, simplify_small=False)
    master_small = render_master(512, simplify_small=True)

    def scaled(sz: int) -> Image.Image:
        src = master_small if sz <= 24 else master_std
        return src.resize((sz, sz), Image.Resampling.LANCZOS)

    # 3. JavaFX PNG sizes
    ui_sizes = [16, 24, 32, 48, 64, 128, 256]
    ui_imgs = {}
    for sz in ui_sizes:
        img = scaled(sz)
        ui_imgs[sz] = img
        img.save(UI_ICONS / f"icon-{sz}.png", format="PNG")

    # 4. Windows multi-size ICO (for jpackage and Win32 taskbar)
    ico_sizes = [256, 128, 64, 48, 32, 24, 16]
    ico_frames = [ui_imgs[sz] for sz in ico_sizes]
    ico_frames[0].save(
        UI_ICONS / "sdnui.ico",
        format="ICO",
        sizes=[(sz, sz) for sz in ico_sizes],
        append_images=ico_frames[1:],
    )

    # 5. Web favicons & touch/PWA icons
    web_ico_sizes = [48, 32, 24, 16]
    web_ico_frames = [ui_imgs[sz] for sz in web_ico_sizes]
    web_ico_frames[0].save(
        SITE_ASSETS / "favicon.ico",
        format="ICO",
        sizes=[(sz, sz) for sz in web_ico_sizes],
        append_images=web_ico_frames[1:],
    )
    scaled(180).save(SITE_ASSETS / "apple-touch-icon.png", format="PNG")
    scaled(192).save(SITE_ASSETS / "icon-192.png", format="PNG")
    scaled(512).save(SITE_ASSETS / "icon-512.png", format="PNG")

    # Verify ICO headers and embedded frames
    for ico_path, expected in [(UI_ICONS / "sdnui.ico", ico_sizes), (SITE_ASSETS / "favicon.ico", web_ico_sizes)]:
        raw = ico_path.read_bytes()
        assert raw[:4] == b"\x00\x00\x01\x00", f"Unexpected ICO header in {ico_path}"
        with Image.open(ico_path) as opened:
            actual_sizes = sorted(opened.info.get("sizes", set()))
            assert actual_sizes == sorted((s, s) for s in expected), f"ICO size mismatch in {ico_path}: {actual_sizes}"
        print(f"Verified {ico_path}: sizes={expected}")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SVG = ROOT / "assets" / "loki-dashboard-icon.svg"
ROOT_ICON = ROOT / "icon.png"
ASSETS_DIR = ROOT / "assets"
WINUI_ASSETS_DIR = ROOT / "winui" / "LokiOperator" / "Assets"


def _star_points(cx: float, cy: float, inner: float, outer: float) -> list[tuple[float, float]]:
    points = []
    spikes = [
        (-0.50, -0.95),
        (-0.18, -0.56),
        (0.00, -1.00),
        (0.18, -0.56),
        (0.50, -0.95),
        (0.36, -0.43),
        (0.86, -0.48),
        (0.48, -0.16),
        (0.88, 0.16),
        (0.36, 0.20),
        (0.45, 0.70),
        (0.08, 0.42),
        (-0.34, 0.72),
        (-0.28, 0.22),
        (-0.82, 0.15),
        (-0.45, -0.16),
        (-0.85, -0.50),
        (-0.36, -0.43),
    ]
    for x, y in spikes:
        scale = outer if abs(y) > 0.55 or abs(x) > 0.7 else inner
        points.append((cx + x * scale, cy + y * scale))
    return points


def render_icon(size: int) -> Image.Image:
    scale = 4
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    s = size * scale
    cx = s * 0.50
    cy = s * 0.47

    draw.rounded_rectangle(
        (s * 0.08, s * 0.08, s * 0.92, s * 0.92),
        radius=int(s * 0.18),
        fill=(16, 18, 24, 255),
        outline=(246, 194, 68, 150),
        width=max(2, int(s * 0.02)),
    )
    draw.polygon(_star_points(cx, cy, s * 0.38, s * 0.40), fill=(246, 194, 68, 255))
    draw.ellipse((s * 0.35, s * 0.37, s * 0.65, s * 0.61), fill=(246, 194, 68, 255))
    draw.rounded_rectangle((s * 0.34, s * 0.59, s * 0.66, s * 0.82), radius=int(s * 0.05), fill=(226, 71, 50, 255))
    draw.line(
        (s * 0.26, s * 0.76, s * 0.43, s * 0.68, s * 0.61, s * 0.74),
        fill=(16, 18, 24, 255),
        width=int(s * 0.035),
    )
    draw.rounded_rectangle(
        (s * 0.26, s * 0.81, s * 0.74, s * 0.88),
        radius=int(s * 0.04),
        fill=(50, 186, 132, 255),
    )
    draw.line(
        (s * 0.34, s * 0.83, s * 0.46, s * 0.88, s * 0.68, s * 0.76),
        fill=(255, 255, 255, 235),
        width=int(s * 0.03),
    )
    for x in (0.34, 0.66):
        draw.ellipse((s * (x - 0.035), s * 0.865, s * (x + 0.035), s * 0.935), fill=(12, 14, 18, 255))

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def centered_canvas(width: int, height: int, icon_size: int, *, background: tuple[int, int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (width, height), background)
    icon = render_icon(icon_size)
    image.alpha_composite(icon, ((width - icon_size) // 2, (height - icon_size) // 2))
    return image


def main() -> int:
    if not SOURCE_SVG.exists():
        raise FileNotFoundError(f"Missing source SVG: {SOURCE_SVG}")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    WINUI_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    render_icon(256).save(ROOT_ICON)
    render_icon(256).save(ASSETS_DIR / "loki-dashboard-icon.png")
    render_icon(64).save(ASSETS_DIR / "loki-dashboard-tray.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    render_icon(256).save(WINUI_ASSETS_DIR / "AppIcon.ico", sizes=[(size, size) for size in ico_sizes])

    png_outputs = {
        "LockScreenLogo.scale-200.png": (48, 48, 42, (0, 0, 0, 0)),
        "Square44x44Logo.scale-200.png": (88, 88, 76, (0, 0, 0, 0)),
        "Square44x44Logo.targetsize-24_altform-unplated.png": (24, 24, 22, (0, 0, 0, 0)),
        "Square44x44Logo.targetsize-48_altform-lightunplated.png": (48, 48, 44, (0, 0, 0, 0)),
        "Square150x150Logo.scale-200.png": (300, 300, 220, (0, 0, 0, 0)),
        "StoreLogo.png": (50, 50, 44, (0, 0, 0, 0)),
        "Wide310x150Logo.scale-200.png": (620, 300, 220, (0, 0, 0, 0)),
        "SplashScreen.scale-200.png": (1240, 600, 260, (12, 13, 16, 255)),
    }
    for filename, (width, height, icon_size, background) in png_outputs.items():
        centered_canvas(width, height, icon_size, background=background).save(WINUI_ASSETS_DIR / filename)

    print(f"Generated LOKI THE SUN GOD icon assets from {SOURCE_SVG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

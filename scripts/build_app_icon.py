"""Build multi-size saa_alpha.ico from packaging/icons source PNG."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "packaging" / "icons" / "saa_alpha_icon_source.png"
OUT_PACK = ROOT / "packaging" / "icons" / "saa_alpha.ico"
OUT_ROOT = ROOT / "saa_alpha.ico"


def main() -> int:
    img = Image.open(SRC).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icons = [img.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    OUT_PACK.parent.mkdir(parents=True, exist_ok=True)
    icons[-1].save(
        OUT_PACK,
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[:-1],
    )
    OUT_ROOT.write_bytes(OUT_PACK.read_bytes())
    print(f"OK {OUT_PACK} ({OUT_PACK.stat().st_size} bytes)")
    print(f"OK {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytz
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

W, H = 1600, 900

OUT_DIR = Path(os.environ.get("CARD_OUT_DIR", "/tmp/bamspx_cards"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

ET_TZ = pytz.timezone("America/New_York")

GREEN = (38, 255, 120)
RED = (255, 48, 96)
WHITE = (246, 248, 255)
MUTED = (175, 180, 192)

def _font(size: int, bold: bool = False):
    here = Path(__file__).parent
    candidates = [
        str(here / ("Cairo-Bold.ttf" if bold else "Cairo-Regular.ttf")),
        str(here / "Cairo-Bold.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for p in candidates:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        except Exception:
            pass

    return ImageFont.load_default()

def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _money(v: Any, default: str = "--") -> str:
    try:
        if v is None or v == "":
            return default
        return f"{float(v):.2f}"
    except Exception:
        return str(v) if v is not None else default

def _fmt_volume(v: Any) -> str:
    try:
        n = float(v)
    except Exception:
        return str(v) if v not in (None, "") else "--"

    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.2f}K"
    return str(int(n))

def _load_bg() -> Image.Image:
    bg_path = Path(__file__).with_name("card_bg.png")

    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGB")
    else:
        bg = Image.new("RGB", (W, H), (0, 0, 0))

    bg = ImageOps.fit(
        bg,
        (W, H),
        method=Image.Resampling.LANCZOS,
        centering=(0.56, 0.44),
    )

    return bg.filter(ImageFilter.GaussianBlur(0.05))

def generate_trade_card(
    contract_data: Dict[str, Any],
    current_price: Any = None,
    status: str = "OPEN",
) -> str:

    cd = contract_data or {}

    base = _load_bg().convert("RGBA")

    dark = Image.new("RGBA", (W, H), (0, 0, 0, 150))
    img = Image.alpha_composite(base, dark)

    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)

    for x in range(780):
        alpha = int(130 * (1 - x / 780))
        sd.line((x, 0, x, H), fill=(0, 0, 0, max(alpha, 0)))

    for y in range(H):
        if y > 430:
            alpha = min(130, int((y - 430) / (H - 430) * 130))
            sd.line((0, y, W, y), fill=(0, 0, 0, alpha))

    img = Image.alpha_composite(img, shade)

    d = ImageDraw.Draw(img)

    symbol = str(cd.get("symbol", "SPXW")).strip()

    mid = _to_float(cd.get("mid"), 0.0)
    open_p = _to_float(cd.get("open"), 0.0)
    shown = _to_float(current_price, mid) if current_price is not None else mid

    diff = shown - open_p if open_p else 0.0
    pct = (diff / open_p * 100) if open_p else 0.0

    color = GREEN if diff >= 0 else RED
    sign = "+" if diff >= 0 else ""

    high = cd.get("high", "--")
    low = cd.get("low", "--")
    oi = cd.get("open_interest", cd.get("oi", "--"))
    vol = cd.get("volume", cd.get("vol", "--"))

    f_contract = _font(52, True)
    if len(symbol) > 31:
        f_contract = _font(46, True)

    f_price = _font(175, True)
    f_change = _font(54, True)
    f_time = _font(44, False)
    f_label = _font(46, True)
    f_value = _font(50, True)
    f_icon = _font(46, True)

    d.text((68, 58), symbol, font=f_contract, fill=WHITE)

    d.rounded_rectangle(
        (1320, 48, 1392, 120),
        radius=14,
        outline=(190, 196, 210, 145),
        width=2,
        fill=(20, 22, 28, 85),
    )
    d.text((1356, 82), "•••", font=f_icon, fill=WHITE, anchor="mm")

    d.rounded_rectangle(
        (1425, 48, 1497, 120),
        radius=14,
        outline=(255, 190, 80, 175),
        width=2,
        fill=(155, 94, 22, 220),
    )
    d.text(
        (1461, 84),
        "⚡",
        font=_font(48, True),
        fill=(255, 238, 190),
        anchor="mm",
    )

    shown_text = _money(shown)
    d.text((68, 185), shown_text, font=f_price, fill=color)

    price_w = d.textbbox((0, 0), shown_text, font=f_price)[2]
    change_x = 68 + price_w + 46

    d.text((change_x, 235), f"{sign}{diff:.2f}", font=f_change, fill=color)
    d.text((change_x, 305), f"{sign}{pct:.2f}%", font=f_change, fill=color)

    now_et = datetime.now(ET_TZ)
    d.text(
        (68, 430),
        f"Open {now_et.strftime('%m/%d %H:%M')} ET",
        font=f_time,
        fill=MUTED,
    )

    left_label_x = 68
    left_value_x = 650

    right_label_x = 830
    right_value_x = 1510

    rows_y = [555, 655, 755]

    def row(y, ll, lv, lc, rl, rv, rc):
        d.text((left_label_x, y), ll, font=f_label, fill=WHITE)
        d.text((left_value_x, y), str(lv), font=f_value, fill=lc, anchor="ra")

        d.text((right_label_x, y), rl, font=f_label, fill=WHITE)
        d.text((right_value_x, y), str(rv), font=f_value, fill=rc, anchor="ra")

    row(rows_y[0], "Open", _money(open_p), color, "Mid", _money(mid), WHITE)
    row(rows_y[1], "Open Int", str(oi), WHITE, "Volume", _fmt_volume(vol), WHITE)
    row(rows_y[2], "High", _money(high), color, "Low", _money(low), RED)

    out = OUT_DIR / f"card_{uuid.uuid4().hex}.jpg"
    img.convert("RGB").save(out, "JPEG", quality=98)

    return str(out)

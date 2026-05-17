from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import pytz
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# BAM | SPX clean card generator
# المطلوب:
# - بدون أي إطار خارجي للكارد
# - بدون أي خطوط داخل الجدول
# - بدون أي خطوط تحت البيانات
# - خلفية سوداء نظيفة مع روبوت Watermark خفيف إذا توفر card_bg.png
# - الصورة كاملة 16:9 حتى تظهر بشكل أفضل في التليجرام

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

    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size)
        except Exception:
            pass

    return ImageFont.load_default()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _money(value: Any, default: str = "--") -> str:
    try:
        if value is None or value == "":
            return default
        return f"{float(value):.2f}"
    except Exception:
        return str(value) if value is not None else default


def _fmt_volume(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return str(value) if value not in (None, "") else "--"

    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.2f}K"
    return str(int(n))


def _make_clean_background() -> Image.Image:
    """
    مهم:
    لا نستخدم صورة card_bg.png كخلفية كاملة؛ لأن الخلفية القديمة فيها خطوط وإطار مطبوخة داخل الصورة.
    بدل ذلك نستخدمها فقط لاستخراج جزء الروبوت كـ watermark خفيف جدًا، ونرسم كل شيء فوق خلفية سوداء نظيفة.
    """

    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    bg_path = Path(__file__).with_name("card_bg.png")

    if not bg_path.exists():
        return img

    try:
        raw = Image.open(bg_path).convert("RGBA")

        # نحاول أخذ منطقة الروبوت فقط من منتصف/يمين الصورة، بعيداً عن نصوص السعر والجدول.
        rw, rh = raw.size

        crop_left = int(rw * 0.40)
        crop_top = int(rh * 0.05)
        crop_right = int(rw * 1.00)
        crop_bottom = int(rh * 0.82)

        robot = raw.crop((crop_left, crop_top, crop_right, crop_bottom))

        # تكبير/تصغير الروبوت كعلامة مائية فقط
        target_w = 760
        target_h = int(target_w * robot.height / max(robot.width, 1))
        robot = robot.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # تغميق الروبوت بقوة حتى لا تظهر الخطوط القديمة إن كانت موجودة
        dark = Image.new("RGBA", robot.size, (0, 0, 0, 145))
        robot = Image.alpha_composite(robot, dark)
        robot = robot.filter(ImageFilter.GaussianBlur(0.25))

        # Alpha خفيف جداً
        alpha = robot.getchannel("A").point(lambda p: int(p * 0.38))
        robot.putalpha(alpha)

        # وضع الروبوت يمين/أعلى مثل التصميم
        x = 780
        y = 10
        img.alpha_composite(robot, (x, y))

    except Exception:
        pass

    return img


def generate_trade_card(
    contract_data: Dict[str, Any],
    current_price: Any = None,
    status: str = "OPEN",
) -> str:

    cd = contract_data or {}

    img = _make_clean_background()

    # تظليل يسار وأسفل فقط — بدون خطوط وبدون إطارات
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)

    for x in range(780):
        alpha = int(105 * (1 - x / 780))
        sd.line((x, 0, x, H), fill=(0, 0, 0, max(alpha, 0)))

    for y in range(H):
        if y > 430:
            alpha = min(120, int((y - 430) / (H - 430) * 120))
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

    f_price = _font(176, True)
    f_change = _font(54, True)
    f_time = _font(44, False)
    f_label = _font(46, True)
    f_value = _font(50, True)
    f_icon = _font(46, True)

    # عنوان العقد
    d.text((68, 58), symbol, font=f_contract, fill=WHITE)

    # أيقونات فقط، بدون إطار للكارد
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

    # السعر
    shown_text = _money(shown)
    d.text((68, 185), shown_text, font=f_price, fill=color)

    price_w = d.textbbox((0, 0), shown_text, font=f_price)[2]
    change_x = 68 + price_w + 46

    d.text((change_x, 235), f"{sign}{diff:.2f}", font=f_change, fill=color)
    d.text((change_x, 305), f"{sign}{pct:.2f}%", font=f_change, fill=color)

    # وقت الافتتاح
    now_et = datetime.now(ET_TZ)
    d.text(
        (68, 430),
        f"Open {now_et.strftime('%m/%d %H:%M')} ET",
        font=f_time,
        fill=MUTED,
    )

    # جدول البيانات — بدون أي خطوط نهائياً
    left_label_x = 68
    left_value_x = 650

    right_label_x = 830
    right_value_x = 1510

    rows_y = [555, 655, 755]

    def row(y, left_label, left_value, left_color, right_label, right_value, right_color):
        d.text((left_label_x, y), left_label, font=f_label, fill=WHITE)
        d.text((left_value_x, y), str(left_value), font=f_value, fill=left_color, anchor="ra")

        d.text((right_label_x, y), right_label, font=f_label, fill=WHITE)
        d.text((right_value_x, y), str(right_value), font=f_value, fill=right_color, anchor="ra")

    row(rows_y[0], "Open", _money(open_p), color, "Mid", _money(mid), WHITE)
    row(rows_y[1], "Open Int", str(oi), WHITE, "Volume", _fmt_volume(vol), WHITE)
    row(rows_y[2], "High", _money(high), color, "Low", _money(low), RED)

    out = OUT_DIR / f"card_{uuid.uuid4().hex}.jpg"
    img.convert("RGB").save(out, "JPEG", quality=98)

    return str(out)

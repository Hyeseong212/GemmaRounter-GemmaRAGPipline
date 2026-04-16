#!/usr/bin/env python3

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path("/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline")
PRESENTATION = ROOT / "presentation"
FIGURES = PRESENTATION / "figures"
RENDERED = FIGURES / "rendered"
SHARED_IMAGE = (
    ROOT
    / "oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/images/transport_room_shared_01.jpg"
)
SHARED_METADATA = (
    ROOT
    / "oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/results/obstacle_metadata.json"
)
USER_REPORT = Path("/home/rbiotech-server/Downloads/병원 이미지/장애물_서술형_결과.txt")
USER_DIR = Path("/home/rbiotech-server/Downloads/병원 이미지")

BG = "#F7F6F3"
TEXT = "#17212B"
SUBTEXT = "#425466"
ACCENT = "#1B6EF3"
ACCENT_2 = "#E85D3F"
ACCENT_3 = "#0F9D58"
BOX = "#E9F0FB"
LINE = "#9DB4D6"


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf" if bold else "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


FONT_TITLE = font(38, bold=True)
FONT_SUBTITLE = font(24, bold=True)
FONT_TEXT = font(20)
FONT_SMALL = font(16)
FONT_LABEL = font(18, bold=True)


def new_canvas(width: int = 1600, height: int = 900) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), BG)
    return img, ImageDraw.Draw(img)


def draw_round_box(draw: ImageDraw.ImageDraw, xy, fill, outline=None, radius=24, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_arrow(draw: ImageDraw.ImageDraw, start, end, color=ACCENT, width=5):
    draw.line([start, end], fill=color, width=width)
    ex, ey = end
    sx, sy = start
    angle = math.atan2(ey - sy, ex - sx)
    size = 14
    left = (ex - size * math.cos(angle - math.pi / 6), ey - size * math.sin(angle - math.pi / 6))
    right = (ex - size * math.cos(angle + math.pi / 6), ey - size * math.sin(angle + math.pi / 6))
    draw.polygon([end, left, right], fill=color)


def fit_image(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    copy = img.copy()
    copy.thumbnail((box_w, box_h))
    return copy


def build_pipeline_diagram():
    img, draw = new_canvas()
    draw.text((70, 48), "System Pipeline", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "OAK camera, Gemma 4 inference, coordinate transform, depth lookup", font=FONT_TEXT, fill=SUBTEXT)

    boxes = [
        ((60, 220, 300, 360), "OAK Camera", "RGB / Depth"),
        ((360, 220, 640, 360), "Gemma 4 /infer", "class + location_yx_1000"),
        ((700, 220, 1010, 360), "Coordinate Transform", "normalized -> pixel -> math"),
        ((1070, 220, 1370, 360), "Depth ROI", "median depth"),
    ]
    for xy, title, subtitle in boxes:
        draw_round_box(draw, xy, BOX, outline=LINE)
        draw.text((xy[0] + 20, xy[1] + 32), title, font=FONT_SUBTITLE, fill=TEXT)
        draw.text((xy[0] + 20, xy[1] + 86), subtitle, font=FONT_TEXT, fill=SUBTEXT)

    for i in range(len(boxes) - 1):
        start = (boxes[i][0][2], 290)
        end = (boxes[i + 1][0][0], 290)
        draw_arrow(draw, start, end)

    draw_round_box(draw, (250, 520, 1170, 760), "#FFFFFF", outline="#D6DCE5")
    bullets = [
        "1. OAK에서 RGB와 Depth를 취득한다.",
        "2. Gemma 4가 이미지에서 장애물 클래스와 위치를 추론한다.",
        "3. location_yx_1000를 픽셀 좌표로 변환한다.",
        "4. 최종적으로 좌하단 원점 수학 좌표와 depth를 결합한다.",
    ]
    y = 560
    for bullet in bullets:
        draw.text((300, y), bullet, font=FONT_TEXT, fill=TEXT)
        y += 46

    img.save(RENDERED / "01_system_pipeline.png")


def build_as_is_to_be_diagram():
    img, draw = new_canvas()
    draw.line((120, 760, 1500, 760), fill=TEXT, width=5)
    draw.line((120, 760, 120, 165), fill=TEXT, width=5)
    draw.text((1430, 778), "환경 복잡도", font=FONT_TEXT, fill=TEXT)
    draw.text((26, 172), "자율성", font=FONT_TEXT, fill=TEXT)

    draw.line((460, 200, 460, 760), fill="#D6DCE5", width=2)
    draw.line((860, 200, 860, 760), fill="#D6DCE5", width=2)

    draw_round_box(draw, (165, 555, 455, 680), "#EEF2F7", outline="#B9C5D4", radius=24, width=3)
    draw.text((262, 575), "AS-IS", font=FONT_SUBTITLE, fill=TEXT)
    draw.text((205, 618), "장애물 존재 여부 중심", font=FONT_TEXT, fill=TEXT)
    draw.text((225, 650), "규칙 기반 회피", font=FONT_TEXT, fill=TEXT)

    draw_round_box(draw, (1030, 200, 1450, 420), "#EAF1FB", outline=ACCENT, radius=28, width=4)
    draw.text((1185, 228), "TO-BE", font=FONT_SUBTITLE, fill=ACCENT)
    draw.text((1098, 278), "병원 장애물의 의미 이해 +", font=FONT_TEXT, fill=TEXT)
    draw.text((1100, 312), "좌표/거리 기반 행동 판단", font=FONT_TEXT, fill=TEXT)
    draw.text((1116, 366), "양보·대기·우회 행동 의사결정", font=FONT_SMALL, fill=SUBTEXT)

    points = [
        (145, 628, "정적 복도 / 단순 주행", ACCENT, (125, 705, 305, 742)),
        (405, 590, "병실 진입 / 좁은 회전", ACCENT_2, (330, 646, 480, 683)),
        (615, 515, "복도 혼잡 / 사람·카트 공존", ACCENT_3, (520, 575, 715, 612)),
        (825, 435, "장애물 분류 + 위치 추론", "#8E44AD", (735, 492, 910, 529)),
        (980, 302, "양보·대기·우회 판단", "#F39C12", (905, 445, 1095, 482)),
    ]
    for x, y, label, color, label_box in points:
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=color, outline=color)
        draw_round_box(draw, label_box, "#FFFFFF", outline="#D6DCE5", radius=16, width=2)
        draw.text((label_box[0] + 10, label_box[1] + 8), label, font=FONT_SMALL, fill=TEXT)

    draw_arrow(draw, (455, 560), (1010, 325), color="#C7771A", width=9)
    draw_round_box(draw, (980, 540, 1450, 700), "#FFFFFF", outline="#D6DCE5", radius=22, width=2)
    draw.text((1015, 565), "핵심 도전 요소", font=FONT_LABEL, fill=ACCENT_2)
    bullets = [
        "① 복도/병실 환경은 비정형적이다.",
        "② 사람과 의료 장비가 계속 바뀐다.",
        "③ 단순 회피가 아니라 의미 기반 대응이 필요하다.",
    ]
    y = 612
    for bullet in bullets:
        draw.text((1015, y), bullet, font=FONT_TEXT, fill=TEXT)
        y += 34

    img.save(RENDERED / "00_as_is_to_be.png")


def build_coordinate_diagram():
    img, draw = new_canvas()
    draw.text((70, 48), "Coordinate Transform", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "Gemma output uses normalized [y, x]; the robot uses bottom-left [x, y]", font=FONT_TEXT, fill=SUBTEXT)

    draw_round_box(draw, (70, 180, 470, 760), "#FFFFFF", outline="#D6DCE5")
    draw.text((110, 205), "Model Output", font=FONT_SUBTITLE, fill=TEXT)
    draw.text((110, 270), "location_yx_1000 = [y, x]", font=FONT_LABEL, fill=ACCENT)
    draw.text((110, 330), "- y: vertical (top to bottom)", font=FONT_TEXT, fill=TEXT)
    draw.text((110, 372), "- x: horizontal (left to right)", font=FONT_TEXT, fill=TEXT)
    draw.text((110, 448), "Pixel conversion", font=FONT_LABEL, fill=ACCENT_2)
    draw.text((110, 500), "x_px = raw_x / 1000 * width", font=FONT_TEXT, fill=TEXT)
    draw.text((110, 542), "y_img = raw_y / 1000 * height", font=FONT_TEXT, fill=TEXT)

    draw_round_box(draw, (560, 180, 1520, 760), "#FFFFFF", outline="#D6DCE5")
    draw.text((600, 205), "Robot Coordinate", font=FONT_SUBTITLE, fill=TEXT)
    draw.rectangle((670, 300, 1270, 640), outline=ACCENT, width=4)
    draw.line((670, 640, 1270, 640), fill=TEXT, width=3)
    draw.line((670, 640, 670, 300), fill=TEXT, width=3)
    draw.text((650, 648), "(0,0)", font=FONT_SMALL, fill=TEXT)
    draw.text((1265, 648), "x", font=FONT_TEXT, fill=TEXT)
    draw.text((640, 290), "y", font=FONT_TEXT, fill=TEXT)
    draw.ellipse((930, 450, 950, 470), fill=ACCENT_3)
    draw.text((970, 440), "Obstacle point [x_math, y_math]", font=FONT_TEXT, fill=TEXT)
    draw.text((600, 700), "y_math = image_height - y_img", font=FONT_LABEL, fill=ACCENT_3)

    draw_arrow(draw, (470, 470), (560, 470), color=ACCENT_2, width=6)

    img.save(RENDERED / "02_coordinate_transform.png")


def build_oak_depth_diagram():
    img, draw = new_canvas()
    draw.text((70, 48), "OAK Depth Integration", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "Obstacle point -> ROI -> median depth", font=FONT_TEXT, fill=SUBTEXT)

    steps = [
        ("RGB Frame", "input image"),
        ("Obstacle Point", "Gemma 4 result"),
        ("ROI Selection", "around [x, y]"),
        ("Depth Median", "distance estimate"),
    ]
    x = 80
    centers = []
    for title, subtitle in steps:
        draw_round_box(draw, (x, 270, x + 300, 430), BOX, outline=LINE)
        draw.text((x + 24, 314), title, font=FONT_SUBTITLE, fill=TEXT)
        draw.text((x + 24, 370), subtitle, font=FONT_TEXT, fill=SUBTEXT)
        centers.append((x + 300, 350))
        x += 360
    for i in range(len(centers) - 1):
        draw_arrow(draw, centers[i], (centers[i + 1][0] - 300, 350))

    draw_round_box(draw, (200, 540, 1400, 760), "#FFFFFF", outline="#D6DCE5")
    notes = [
        "RGB와 depth를 동시에 취득한다.",
        "Gemma 4가 반환한 좌표를 depth 프레임 좌표계로 맞춘다.",
        "작은 ROI(예: 21x21)에서 유효 depth만 취합한다.",
        "median depth를 대표 거리로 사용한다.",
    ]
    y = 585
    for note in notes:
        draw.text((250, y), note, font=FONT_TEXT, fill=TEXT)
        y += 42

    img.save(RENDERED / "03_oak_depth_flow.png")


def build_robot_framework_diagram():
    img, draw = new_canvas()
    draw.text((70, 48), "병원 장애물 인지 프레임워크", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "인지, 의미 이해, 공간 정렬, 행동 판단을 하나의 흐름으로 구성", font=FONT_TEXT, fill=SUBTEXT)

    layers = [
        (120, 190, 1480, 300, "#EAF1FB", ACCENT, "1. 인지 계층", "OAK RGB / Depth, 병원 장면 입력, 프레임 수집"),
        (170, 330, 1430, 440, "#FFF4EE", ACCENT_2, "2. 의미 이해 계층", "Gemma 4 기반 장애물 클래스 추론, 장면 의미 해석"),
        (220, 470, 1380, 580, "#EEF7F0", ACCENT_3, "3. 공간 정렬 계층", "normalized [y,x] -> 픽셀 -> bottom-left 수학좌표 + ROI depth"),
        (270, 610, 1330, 730, "#F3EEFB", "#7C4DFF", "4. 행동 판단 계층", "양보 / 대기 / 우회 / 음성 안내 / 로봇 주행 입력"),
    ]
    for x1, y1, x2, y2, fill, color, title, subtitle in layers:
        draw_round_box(draw, (x1, y1, x2, y2), fill, outline=color, radius=28, width=3)
        draw.text((x1 + 28, y1 + 22), title, font=FONT_SUBTITLE, fill=color)
        draw.text((x1 + 28, y1 + 62), subtitle, font=FONT_TEXT, fill=TEXT)

    draw_arrow(draw, (800, 300), (800, 330), color=ACCENT, width=6)
    draw_arrow(draw, (800, 440), (800, 470), color=ACCENT_2, width=6)
    draw_arrow(draw, (800, 580), (800, 610), color=ACCENT_3, width=6)

    draw_round_box(draw, (1120, 610, 1330, 730), "#FFFFFF", outline="#D6DCE5")
    draw.text((1145, 635), "예시 로봇 멘트", font=FONT_LABEL, fill="#7C4DFF")
    draw.text((1140, 672), "“전방에 의료진이 있습니다.\n잠시 대기 후 이동하겠습니다.”", font=FONT_SMALL, fill=TEXT)

    img.save(RENDERED / "08_robot_framework.png")


def build_shared_room_overlay():
    image = Image.open(SHARED_IMAGE).convert("RGB")
    data = json.load(open(SHARED_METADATA, encoding="utf-8"))[0]
    draw = ImageDraw.Draw(image)
    colors = [ACCENT, ACCENT_2, ACCENT_3, "#8E44AD", "#FF9800", "#0097A7"]
    for idx, obstacle in enumerate(data["obstacles"], start=1):
        x, y = obstacle["pixel_top_left"]
        color = colors[(idx - 1) % len(colors)]
        r = 18
        draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=6)
        label = f"{idx}. {obstacle['class_name']}"
        tx = min(max(20, x + 28), image.width - 340)
        ty = min(max(20, y - 20), image.height - 60)
        draw_round_box(draw, (tx, ty, tx + 280, ty + 42), fill="#FFFFFF", outline=color, radius=14, width=3)
        draw.text((tx + 12, ty + 10), label, font=FONT_SMALL, fill=TEXT)
    image.save(RENDERED / "04_shared_room_overlay.png", quality=95)


def build_user_contact_sheet():
    files = sorted([p for p in USER_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}])
    thumbs = []
    for file in files:
        img = Image.open(file).convert("RGB")
        img = fit_image(img, 300, 180)
        canvas = Image.new("RGB", (330, 230), "white")
        canvas.paste(img, ((330 - img.width) // 2, 10))
        d = ImageDraw.Draw(canvas)
        d.text((12, 195), file.name, font=FONT_SMALL, fill=TEXT)
        thumbs.append(canvas)
    cols = 4
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 330, rows * 230), BG)
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % cols) * 330, (i // cols) * 230))
    sheet.save(RENDERED / "05_user_samples_contact_sheet.png", quality=95)


def parse_report_counts() -> Counter:
    text = USER_REPORT.read_text(encoding="utf-8")
    classes = re.findall(r"클래스: ([a-zA-Z_]+)", text)
    return Counter(classes)


def build_class_frequency_chart():
    counts = parse_report_counts()
    items = counts.most_common(8)
    img, draw = new_canvas()
    draw.text((70, 48), "Obstacle Class Frequency", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "Top classes from 8 user-provided hospital images", font=FONT_TEXT, fill=SUBTEXT)
    origin_x = 220
    origin_y = 760
    chart_h = 520
    max_v = max(v for _, v in items) if items else 1
    draw.line((origin_x, origin_y - chart_h, origin_x, origin_y), fill=TEXT, width=3)
    draw.line((origin_x, origin_y, 1450, origin_y), fill=TEXT, width=3)
    bar_w = 110
    gap = 30
    x = origin_x + 40
    palette = [ACCENT, ACCENT_2, ACCENT_3, "#8E44AD", "#F9A825", "#00897B", "#6D4C41", "#3949AB"]
    for idx, (label, value) in enumerate(items):
        h = int((value / max_v) * (chart_h - 40))
        top = origin_y - h
        color = palette[idx % len(palette)]
        draw_round_box(draw, (x, top, x + bar_w, origin_y), fill=color, outline=color, radius=18)
        draw.text((x + 35, top - 34), str(value), font=FONT_SMALL, fill=TEXT)
        draw.text((x - 5, origin_y + 10), label, font=FONT_SMALL, fill=TEXT)
        x += bar_w + gap
    img.save(RENDERED / "06_class_frequency_chart.png")


def build_result_snapshot_card():
    text = USER_REPORT.read_text(encoding="utf-8").splitlines()
    img, draw = new_canvas()
    draw.text((70, 48), "Batch Result Summary", font=FONT_TITLE, fill=TEXT)
    draw.text((72, 98), "Generated from /home/rbiotech-server/Downloads/병원 이미지", font=FONT_TEXT, fill=SUBTEXT)
    draw_round_box(draw, (70, 170, 1530, 810), "#FFFFFF", outline="#D6DCE5")
    y = 210
    for line in text[:24]:
        draw.text((100, y), line, font=FONT_SMALL, fill=TEXT)
        y += 24
    img.save(RENDERED / "07_batch_result_snapshot.png")


def main():
    RENDERED.mkdir(parents=True, exist_ok=True)
    build_as_is_to_be_diagram()
    build_pipeline_diagram()
    build_coordinate_diagram()
    build_oak_depth_diagram()
    build_robot_framework_diagram()
    build_shared_room_overlay()
    build_user_contact_sheet()
    build_class_frequency_chart()
    build_result_snapshot_card()
    print(RENDERED)


if __name__ == "__main__":
    main()

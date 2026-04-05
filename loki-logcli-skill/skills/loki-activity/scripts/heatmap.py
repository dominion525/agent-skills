# /// script
# requires-python = ">=3.10"
# dependencies = ["rich", "Pillow"]
# ///
"""activity.shのJSON出力からヒートマップを表示する"""

import json
import sys
import os
import argparse
import base64
import io
from datetime import datetime, timezone, timedelta
from typing import NamedTuple

JST = timezone(timedelta(hours=9))

# GitHubの草風パレット（5段階）
PALETTE = [
    (22, 27, 34),     # level 0: データなし（ほぼ黒）
    (14, 68, 41),     # level 1: 薄緑
    (0, 109, 50),     # level 2: 緑
    (38, 166, 65),    # level 3: 明るい緑
    (57, 211, 83),    # level 4: 最も明るい緑
]


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------

class DayGrid(NamedTuple):
    namespace: str
    day_key: str
    metric: str
    interval: int
    slots_per_hour: int
    max_val: int
    levels: list[list[int]]              # [m_idx][col] = 0..4, データなしは -1
    raw_values: list[list[int | None]]   # [m_idx][col] = 元の数値 or None
    hour_labels: list[int]               # 各列の時間ラベル（0-23）


# ---------------------------------------------------------------------------
# 引数・データ読み込み
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="作業アクティビティのヒートマップ表示")
    parser.add_argument("file", nargs="?", default="-", help="JSONファイル (省略でstdin)")

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--color", action="store_true", help="TrueColorモードで表示")
    mode_group.add_argument("--image", action="store_true", help="iTerm2画像モードで表示")

    parser.add_argument("--metric", default="total",
                        choices=["total", "user_prompt", "api_request", "tool_use"],
                        help="表示するメトリクス (デフォルト: total)")
    return parser.parse_args()


def load_data(file_path):
    if file_path == "-":
        return json.load(sys.stdin)
    with open(file_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# グリッド計算（全レンダラー共通）
# ---------------------------------------------------------------------------

def utc_to_jst(utc_str):
    dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def build_grid(project):
    """スロットデータを日付別・時間別のグリッドに変換する"""
    slots = project["slots"]
    interval = project.get("interval_minutes", 10)
    slots_per_hour = 60 // interval

    days = {}
    for slot in slots:
        jst = utc_to_jst(slot["time_utc"])
        day_key = jst.strftime("%m/%d")
        if day_key not in days:
            days[day_key] = {}
        slot_index = jst.hour * slots_per_hour + jst.minute // interval
        days[day_key][slot_index] = slot

    return days, interval, slots_per_hour


def compute_level_matrix(project, metric, num_levels=5):
    """プロジェクトのスロットデータからレベル行列を計算する。
    横軸は現在時刻が右端に来るようにローテーションされる。"""
    slots = project["slots"]
    if not slots:
        return []

    ns = project["namespace"]
    values = [s[metric] for s in slots]
    max_val = max(values) if values else 1

    days, interval, slots_per_hour = build_grid(project)

    # 現在時刻の次の時間を起点にして、24時間分をローテーション
    now_jst = datetime.now(JST)
    start_hour = (now_jst.hour + 1) % 24
    hour_order = [(start_hour + i) % 24 for i in range(24)]

    result = []

    for day_key, hour_map in days.items():
        levels = []
        raw_values = []
        for m_idx in range(slots_per_hour):
            level_row = []
            raw_row = []
            for h in hour_order:
                slot_index = h * slots_per_hour + m_idx
                slot = hour_map.get(slot_index)
                if slot is None:
                    level_row.append(-1)
                    raw_row.append(None)
                else:
                    val = slot[metric]
                    level = min(num_levels - 1, int(val / max(max_val, 1) * (num_levels - 1)) + 1)
                    level_row.append(level)
                    raw_row.append(val)
            levels.append(level_row)
            raw_values.append(raw_row)

        result.append(DayGrid(
            namespace=ns, day_key=day_key, metric=metric,
            interval=interval, slots_per_hour=slots_per_hour,
            max_val=max_val, levels=levels, raw_values=raw_values,
            hour_labels=hour_order,
        ))

    return result


def _merge_overall(grids, metric):
    """複数プロジェクトのグリッドを合算したOverallグリッドを生成する"""
    if len(grids) <= 1:
        return []

    # day_keyごとにグループ化
    by_day = {}
    for g in grids:
        if g.day_key not in by_day:
            by_day[g.day_key] = []
        by_day[g.day_key].append(g)

    result = []
    for day_key, day_grids in by_day.items():
        ref = day_grids[0]
        rows = ref.slots_per_hour

        # raw_valuesを合算
        merged_raw = []
        for m_idx in range(rows):
            raw_row = []
            for col in range(24):
                total = None
                for g in day_grids:
                    val = g.raw_values[m_idx][col]
                    if val is not None:
                        total = (total or 0) + val
                raw_row.append(total)
            merged_raw.append(raw_row)

        # 合算後のmax_valとlevelsを再計算
        all_vals = [v for row in merged_raw for v in row if v is not None]
        max_val = max(all_vals) if all_vals else 1

        merged_levels = []
        for raw_row in merged_raw:
            level_row = []
            for val in raw_row:
                if val is None:
                    level_row.append(-1)
                else:
                    level_row.append(min(4, int(val / max(max_val, 1) * 4) + 1))
            merged_levels.append(level_row)

        result.append(DayGrid(
            namespace="Overall", day_key=day_key, metric=metric,
            interval=ref.interval, slots_per_hour=rows,
            max_val=max_val, levels=merged_levels, raw_values=merged_raw,
            hour_labels=ref.hour_labels,
        ))

    return result


def prepare_all_grids(data, metric):
    """全プロジェクトのグリッドを生成する。複数プロジェクトがある場合はOverallを先頭に追加"""
    grids = []
    for project in data["projects"]:
        grids.extend(compute_level_matrix(project, metric))

    overall = _merge_overall(grids, metric)
    return overall + grids


# ---------------------------------------------------------------------------
# レンダラー: ASCII
# ---------------------------------------------------------------------------

def render_ascii(grids):
    blocks = " \u2591\u2592\u2593\u2588"  # ░▒▓█

    for g in grids:
        print(f"\n[ {g.namespace} ] {g.day_key} metric={g.metric}")

        print("       ", end="")
        for h in g.hour_labels:
            print(f"{h:>3}", end="")
        print()

        for m_idx in range(g.slots_per_hour):
            minute = m_idx * g.interval
            print(f"  :{minute:02d}  ", end="")
            for col in range(24):
                level = g.levels[m_idx][col]
                if level == -1:
                    print("  .", end="")
                else:
                    print(f"  {blocks[level]}", end="")
            print()

    print()


# ---------------------------------------------------------------------------
# レンダラー: TrueColor (rich)
# ---------------------------------------------------------------------------

def render_color(grids):
    from rich.console import Console
    from rich.text import Text

    console = Console()

    for g in grids:
        console.print(f"\n[bold][ {g.namespace} ][/bold] {g.day_key}  metric={g.metric}")

        header = Text("       ")
        for h in g.hour_labels:
            header.append(f"{h:>3}", style="dim")
        console.print(header)

        for m_idx in range(g.slots_per_hour):
            minute = m_idx * g.interval
            line = Text(f"  :{minute:02d}  ")
            for col in range(24):
                level = g.levels[m_idx][col]
                idx = max(0, level)
                r, gc, b = PALETTE[idx]
                line.append(" \u2588\u2588", style=f"rgb({r},{gc},{b})")  # ██
            console.print(line)

        legend = Text("        ")
        legend.append("\u5c11 ", style="dim")  # 少
        for r, gc, b in PALETTE:
            legend.append("\u2588\u2588", style=f"rgb({r},{gc},{b})")  # ██
        legend.append(" \u591a", style="dim")  # 多
        console.print(legend)

    console.print()


# ---------------------------------------------------------------------------
# レンダラー: iTerm2画像
# ---------------------------------------------------------------------------

# 画像レンダリング定数
IMG_CELL_SIZE = 42
IMG_CELL_GAP = 7
IMG_MARGIN_LEFT = 180
IMG_MARGIN_TOP = 110
IMG_MARGIN_BOTTOM = 100
IMG_MARGIN_RIGHT = 30
IMG_BG_COLOR = (13, 17, 23)
IMG_TEXT_COLOR = (139, 148, 158)
IMG_FONT_SIZE = 32


def is_iterm2():
    """現在のターミナルがiTerm2かどうかを判定する"""
    return (
        os.environ.get("TERM_PROGRAM") == "iTerm.app"
        or os.environ.get("LC_TERMINAL") == "iTerm2"
    )


def _get_font(size):
    """フォントを取得する。利用可能なフォントがなければデフォルトを返す"""
    from PIL import ImageFont

    font_candidates = [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/SFMono-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_legend(draw, font, x, y):
    """凡例バーを描画する"""
    draw.text((x, y + 6), "Less", fill=IMG_TEXT_COLOR, font=font)
    box_x = x + 80
    for color in PALETTE:
        draw.rounded_rectangle(
            [box_x, y, box_x + IMG_CELL_SIZE, y + IMG_CELL_SIZE],
            radius=5, fill=color,
        )
        box_x += IMG_CELL_SIZE + IMG_CELL_GAP
    draw.text((box_x + 12, y + 6), "More", fill=IMG_TEXT_COLOR, font=font)


def draw_heatmap_image(g):
    """単一のDayGridからPIL Imageオブジェクトを生成する"""
    from PIL import Image, ImageDraw

    cols = 24
    rows = g.slots_per_hour
    step = IMG_CELL_SIZE + IMG_CELL_GAP

    width = IMG_MARGIN_LEFT + cols * step + IMG_MARGIN_RIGHT
    height = IMG_MARGIN_TOP + rows * step + IMG_MARGIN_BOTTOM

    img = Image.new("RGB", (width, height), IMG_BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = _get_font(IMG_FONT_SIZE)

    # タイトル
    title = f"[ {g.namespace} ] {g.day_key}  metric={g.metric}"
    draw.text((IMG_MARGIN_LEFT, 12), title, fill=(255, 255, 255), font=font)

    # 時間軸ヘッダー
    for col, h in enumerate(g.hour_labels):
        x = IMG_MARGIN_LEFT + col * step + IMG_CELL_SIZE // 2
        draw.text((x, IMG_MARGIN_TOP - 36), str(h), fill=IMG_TEXT_COLOR, font=font, anchor="mt")

    # 左ラベル
    for m_idx in range(rows):
        minute = m_idx * g.interval
        y = IMG_MARGIN_TOP + m_idx * step + IMG_CELL_SIZE // 2
        draw.text((IMG_MARGIN_LEFT - 16, y), f":{minute:02d}", fill=IMG_TEXT_COLOR, font=font, anchor="rm")

    # セル描画
    for m_idx in range(rows):
        for col in range(24):
            x = IMG_MARGIN_LEFT + col * step
            y = IMG_MARGIN_TOP + m_idx * step
            level = g.levels[m_idx][col]
            color = PALETTE[max(0, level)]
            draw.rounded_rectangle(
                [x, y, x + IMG_CELL_SIZE, y + IMG_CELL_SIZE],
                radius=5, fill=color,
            )

    # 凡例
    _draw_legend(draw, font, IMG_MARGIN_LEFT, IMG_MARGIN_TOP + rows * step + 10)

    return img


def emit_iterm2_image(img, name="heatmap.png", width="auto", height="auto"):
    """PIL ImageをiTerm2インライン画像プロトコルで表示する"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    b64_name = base64.b64encode(name.encode()).decode("ascii")
    b64_data = base64.b64encode(png_bytes).decode("ascii")

    params = (
        f"name={b64_name}"
        f";size={len(png_bytes)}"
        f";inline=1"
        f";width={width}"
        f";height={height}"
        f";preserveAspectRatio=1"
    )
    sys.stdout.write(f"\033]1337;File={params}:{b64_data}\a\n")
    sys.stdout.flush()


def render_image(grids):
    """iTerm2画像モードでヒートマップを表示する"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print(
            "エラー: --image オプションには Pillow が必要です。\n"
            "  uv run で実行していれば自動インストールされます。\n"
            "  手動インストール: pip install Pillow",
            file=sys.stderr,
        )
        sys.exit(1)

    for g in grids:
        img = draw_heatmap_image(g)
        emit_iterm2_image(img, name=f"{g.namespace}_{g.day_key}.png")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    data = load_data(args.file)

    if not data.get("projects"):
        print("該当期間にイベントが見つかりませんでした")
        return

    grids = prepare_all_grids(data, args.metric)

    if args.image:
        if not is_iterm2():
            print(
                "警告: iTerm2が検出されませんでした。"
                "画像が正しく表示されない可能性があります。",
                file=sys.stderr,
            )
        render_image(grids)
    elif args.color:
        render_color(grids)
    else:
        render_ascii(grids)


if __name__ == "__main__":
    main()

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
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from PIL import Image

JST = timezone(timedelta(hours=9))

# GitHubの草風パレット（5段階）
PALETTE = [
    (22, 27, 34),  # level 0: データなし（ほぼ黒）
    (14, 68, 41),  # level 1: 薄緑
    (0, 109, 50),  # level 2: 緑
    (38, 166, 65),  # level 3: 明るい緑
    (57, 211, 83),  # level 4: 最も明るい緑
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
    levels: list[list[int]]  # [m_idx][col] = 0..4, データなしは -1
    raw_values: list[list[int | None]]  # [m_idx][col] = 元の数値 or None
    hour_labels: list[int]  # 各列の時間ラベル（0-23）


# ---------------------------------------------------------------------------
# 引数・データ読み込み
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="作業アクティビティのヒートマップ表示")
    parser.add_argument(
        "file", nargs="?", default="-", help="JSONファイル (省略でstdin)"
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--color", action="store_true", help="TrueColorモードで表示"
    )
    mode_group.add_argument(
        "--image", action="store_true", help="iTerm2画像モードで表示"
    )
    mode_group.add_argument("--output", metavar="FILE", help="画像をファイルに保存")

    parser.add_argument(
        "--metric",
        default="total",
        choices=["total", "user_prompt", "api_request", "tool_use"],
        help="表示するメトリクス (デフォルト: total)",
    )
    parser.add_argument("--overall", action="store_true", help="Overallのみ表示")
    return parser.parse_args()


def load_data(file_path: str) -> dict:
    if file_path == "-":
        return json.load(sys.stdin)
    with open(file_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# グリッド計算（全レンダラー共通）
# ---------------------------------------------------------------------------


def utc_to_jst(utc_str: str) -> datetime:
    dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def build_grid(project: dict) -> tuple[dict[str, dict[int, dict]], int, int]:
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


def _value_to_level(val: int | None, max_val: int, num_levels: int = 5) -> int:
    """値からヒートマップのレベル（0..num_levels-1）を計算する。Noneは-1を返す"""
    if val is None:
        return -1
    return min(num_levels - 1, int(val / max(max_val, 1) * (num_levels - 1)) + 1)


def _rotated_hours(current_hour: int) -> list[int]:
    """current_hourの次の時間を起点にした24時間分のリストを返す"""
    start = (current_hour + 1) % 24
    return [(start + i) % 24 for i in range(24)]


def compute_level_matrix(
    project: dict, metric: str, num_levels: int = 5
) -> list[DayGrid]:
    """プロジェクトのスロットデータからレベル行列を計算する。
    横軸は現在時刻が右端に来るようにローテーションされる。
    日をまたいだデータも1つのDayGridに統合する。"""
    slots = project["slots"]
    if not slots:
        return []

    ns = project["namespace"]
    days, interval, slots_per_hour = build_grid(project)
    hour_order = _rotated_hours(datetime.now(JST).hour)

    # 全日のスロットを1つのhour_mapに統合（同じslot_indexは値を合算）
    merged_map: dict[int, dict] = {}
    for hour_map in days.values():
        for slot_index, slot in hour_map.items():
            if slot_index in merged_map:
                existing = merged_map[slot_index]
                merged_map[slot_index] = {
                    k: existing.get(k, 0) + slot.get(k, 0)
                    for k in slot
                    if k != "time_utc"
                }
                merged_map[slot_index]["time_utc"] = slot["time_utc"]
            else:
                merged_map[slot_index] = dict(slot)

    # max_valを統合後のデータで再計算
    max_val = max((s[metric] for s in merged_map.values()), default=1)

    # 1つのDayGridを生成
    today_key = datetime.now(JST).strftime("%m/%d")
    levels = []
    raw_values = []
    for m_idx in range(slots_per_hour):
        level_row = []
        raw_row = []
        for h in hour_order:
            slot_index = h * slots_per_hour + m_idx
            slot = merged_map.get(slot_index)
            if slot is None:
                level_row.append(-1)
                raw_row.append(None)
            else:
                val = slot[metric]
                level_row.append(_value_to_level(val, max_val, num_levels))
                raw_row.append(val)
        levels.append(level_row)
        raw_values.append(raw_row)

    return [
        DayGrid(
            namespace=ns,
            day_key=today_key,
            metric=metric,
            interval=interval,
            slots_per_hour=slots_per_hour,
            max_val=max_val,
            levels=levels,
            raw_values=raw_values,
            hour_labels=hour_order,
        )
    ]


def _merge_overall(grids: list[DayGrid], metric: str) -> list[DayGrid]:
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
                        if total is None:
                            total = val
                        else:
                            total += val
                raw_row.append(total)
            merged_raw.append(raw_row)

        # 合算後のmax_valとlevelsを再計算
        all_vals = [v for row in merged_raw for v in row if v is not None]
        max_val = max(all_vals, default=1)

        merged_levels = [
            [_value_to_level(val, max_val) for val in raw_row] for raw_row in merged_raw
        ]

        result.append(
            DayGrid(
                namespace="Overall",
                day_key=day_key,
                metric=metric,
                interval=ref.interval,
                slots_per_hour=rows,
                max_val=max_val,
                levels=merged_levels,
                raw_values=merged_raw,
                hour_labels=ref.hour_labels,
            )
        )

    return result


def prepare_all_grids(data: dict, metric: str) -> list[DayGrid]:
    """全プロジェクトのグリッドを生成する。複数プロジェクトがある場合はOverallを先頭に追加"""
    grids = []
    for project in data["projects"]:
        grids.extend(compute_level_matrix(project, metric))

    overall = _merge_overall(grids, metric)
    return overall + grids


# ---------------------------------------------------------------------------
# レンダラー: ASCII
# ---------------------------------------------------------------------------


def render_ascii(grids: list[DayGrid]) -> None:
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


def render_color(grids: list[DayGrid]) -> None:
    from rich.console import Console
    from rich.text import Text

    console = Console()

    for g in grids:
        console.print(
            f"\n[bold][ {g.namespace} ][/bold] {g.day_key}  metric={g.metric}"
        )

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
# 描画命令（宣言的レンダリング）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextCmd:
    """テキスト描画命令"""

    pos: tuple[int, int]
    text: str
    color: tuple[int, int, int]
    anchor: str | None = None


@dataclass(frozen=True)
class RectCmd:
    """矩形描画命令"""

    rect: tuple[int, int, int, int]
    color: tuple[int, int, int]
    radius: int = 0


DrawCommand = TextCmd | RectCmd


# ---------------------------------------------------------------------------
# レンダラー: iTerm2画像
# ---------------------------------------------------------------------------

# スタイル設定（レイアウトに属さない色・フォント）
IMG_BG_COLOR = (13, 17, 23)
IMG_TEXT_COLOR = (139, 148, 158)
IMG_FONT_SIZE = 32


@dataclass
class HeatmapLayout:
    """ヒートマップ画像のレイアウト計算を担うモデル"""

    rows: int
    cols: int = 24
    cell_size: int = 42
    cell_gap: int = 7
    margin_left: int = 180
    margin_top: int = 110
    margin_bottom: int = 100
    margin_right: int = 30
    cell_radius: int = 5
    title_y: int = 12
    header_offset: int = 36
    label_offset: int = 16
    legend_gap: int = 10

    @property
    def step(self) -> int:
        return self.cell_size + self.cell_gap

    @property
    def width(self) -> int:
        return self.margin_left + self.cols * self.step + self.margin_right

    @property
    def height(self) -> int:
        return self.margin_top + self.rows * self.step + self.margin_bottom

    def cell_rect(self, row: int, col: int) -> list[int]:
        """セル(row, col)の矩形座標 [x0, y0, x1, y1]"""
        x = self.margin_left + col * self.step
        y = self.margin_top + row * self.step
        return [x, y, x + self.cell_size, y + self.cell_size]

    def cell_center(self, row: int, col: int) -> tuple[int, int]:
        """セル(row, col)の中心座標 (cx, cy)"""
        x = self.margin_left + col * self.step + self.cell_size // 2
        y = self.margin_top + row * self.step + self.cell_size // 2
        return (x, y)

    def title_pos(self) -> tuple[int, int]:
        """タイトルテキストの座標"""
        return (self.margin_left, self.title_y)

    def header_pos(self, col: int) -> tuple[int, int]:
        """時間軸ヘッダーのテキスト座標（anchor="mt"用）"""
        x = self.margin_left + col * self.step + self.cell_size // 2
        y = self.margin_top - self.header_offset
        return (x, y)

    def label_pos(self, row: int) -> tuple[int, int]:
        """左ラベルのテキスト座標（anchor="rm"用）"""
        x = self.margin_left - self.label_offset
        y = self.margin_top + row * self.step + self.cell_size // 2
        return (x, y)

    def legend_pos(self) -> tuple[int, int]:
        """凡例バーの基準座標 (x, y)"""
        x = self.margin_left
        y = self.margin_top + self.rows * self.step + self.legend_gap
        return (x, y)


def build_heatmap_commands(
    g: DayGrid,
    layout: HeatmapLayout,
    palette: list[tuple[int, int, int]] = PALETTE,
    text_color: tuple[int, int, int] = IMG_TEXT_COLOR,
    title_color: tuple[int, int, int] = (255, 255, 255),
    now: datetime | None = None,
) -> list[DrawCommand]:
    """ヒートマップの描画命令リストを生成する。純粋関数。"""
    now = now or datetime.now(JST)
    commands: list[DrawCommand] = []

    # 未来スロット判定の準備
    today_key = now.strftime("%m/%d")
    is_today = g.day_key == today_key
    last_col = layout.cols - 1
    now_minute_slot = now.minute // g.interval

    # タイトル
    commands.append(
        TextCmd(
            layout.title_pos(),
            f"[ {g.namespace} ] {g.day_key}  metric={g.metric}",
            title_color,
        )
    )

    # 時間軸ヘッダー
    for col, h in enumerate(g.hour_labels):
        commands.append(
            TextCmd(layout.header_pos(col), str(h), text_color, anchor="mt")
        )

    # 左ラベル
    for m_idx in range(layout.rows):
        minute = m_idx * g.interval
        commands.append(
            TextCmd(layout.label_pos(m_idx), f":{minute:02d}", text_color, anchor="rm")
        )

    # セル（未来のスロットはスキップ）
    for m_idx in range(layout.rows):
        for col in range(layout.cols):
            if is_today and col == last_col and m_idx > now_minute_slot:
                continue
            level = g.levels[m_idx][col]
            color = palette[max(0, level)]
            commands.append(
                RectCmd(
                    tuple(layout.cell_rect(m_idx, col)),
                    color,
                    radius=layout.cell_radius,
                )
            )

    # 凡例
    _build_legend_commands(commands, layout, palette, text_color)

    return commands


def _build_legend_commands(
    commands: list[DrawCommand],
    layout: HeatmapLayout,
    palette: list[tuple[int, int, int]],
    text_color: tuple[int, int, int],
    label_left: str = "Less",
    label_right: str = "More",
    label_width: int = 80,
    end_margin: int = 12,
    text_offset_y: int = 6,
) -> None:
    """凡例の描画命令をcommandsに追加する"""
    lx, ly = layout.legend_pos()

    commands.append(TextCmd((lx, ly + text_offset_y), label_left, text_color))

    box_x = lx + label_width
    for color in palette:
        commands.append(
            RectCmd(
                (box_x, ly, box_x + layout.cell_size, ly + layout.cell_size),
                color,
                radius=layout.cell_radius,
            )
        )
        box_x += layout.step

    commands.append(
        TextCmd((box_x + end_margin, ly + text_offset_y), label_right, text_color)
    )


def render_commands(
    commands: list[DrawCommand],
    width: int,
    height: int,
    bg_color: tuple[int, int, int],
    font,
) -> "Image.Image":
    """描画命令リストからPIL Imageを生成する"""
    from PIL import Image as PILImage
    from PIL import ImageDraw

    img = PILImage.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    for cmd in commands:
        if isinstance(cmd, TextCmd):
            kwargs = {}
            if cmd.anchor is not None:
                kwargs["anchor"] = cmd.anchor
            draw.text(cmd.pos, cmd.text, fill=cmd.color, font=font, **kwargs)
        elif isinstance(cmd, RectCmd):
            if cmd.radius > 0:
                draw.rounded_rectangle(cmd.rect, radius=cmd.radius, fill=cmd.color)
            else:
                draw.rectangle(cmd.rect, fill=cmd.color)

    return img


def is_iterm2() -> bool:
    """現在のターミナルがiTerm2かどうかを判定する"""
    return (
        os.environ.get("TERM_PROGRAM") == "iTerm.app"
        or os.environ.get("LC_TERMINAL") == "iTerm2"
    )


def _get_font(size: int):
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


def draw_heatmap_image(
    g: DayGrid, layout: HeatmapLayout | None = None
) -> "Image.Image":
    """単一のDayGridからPIL Imageオブジェクトを生成する"""
    layout = layout or HeatmapLayout(rows=g.slots_per_hour)
    commands = build_heatmap_commands(g, layout)
    font = _get_font(IMG_FONT_SIZE)
    return render_commands(commands, layout.width, layout.height, IMG_BG_COLOR, font)


def emit_iterm2_image(
    img: "Image.Image",
    name: str = "heatmap.png",
    width: str = "auto",
    height: str = "auto",
) -> None:
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


def save_image(grids: list[DayGrid], path: str) -> None:
    """全グリッドの画像を縦に連結してファイルに保存する"""
    from PIL import Image

    images = [draw_heatmap_image(g) for g in grids]
    if not images:
        return

    total_width = max(img.width for img in images)
    total_height = sum(img.height for img in images)
    combined = Image.new("RGB", (total_width, total_height), IMG_BG_COLOR)

    y_offset = 0
    for img in images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    combined.save(path)
    print(f"{path} に保存しました ({total_width}x{total_height})")


def render_image(grids: list[DayGrid]) -> None:
    """iTerm2画像モードでヒートマップを表示する"""
    try:
        import PIL  # noqa: F401
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


def main() -> None:
    args = parse_args()
    data = load_data(args.file)

    if not data.get("projects"):
        print("該当期間にイベントが見つかりませんでした")
        return

    grids = prepare_all_grids(data, args.metric)

    if args.overall:
        grids = [g for g in grids if g.namespace == "Overall"]
        if not grids:
            print("Overallデータがありません（複数プロジェクトが必要です）")
            return

    if args.output:
        save_image(grids, args.output)
    elif args.image:
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

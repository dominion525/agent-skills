# /// script
# requires-python = ">=3.10"
# dependencies = ["rich"]
# ///
"""activity.shのJSON出力からヒートマップを表示する"""

import json
import sys
import argparse
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))


def parse_args():
    parser = argparse.ArgumentParser(description="作業アクティビティのヒートマップ表示")
    parser.add_argument("file", nargs="?", default="-", help="JSONファイル (省略でstdin)")
    parser.add_argument("--color", action="store_true", help="TrueColorモードで表示")
    parser.add_argument("--metric", default="total", choices=["total", "user_prompt", "api_request", "tool_use"],
                        help="表示するメトリクス (デフォルト: total)")
    return parser.parse_args()


def load_data(file_path):
    if file_path == "-":
        return json.load(sys.stdin)
    with open(file_path) as f:
        return json.load(f)


def utc_to_jst(utc_str):
    dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(JST)


def build_grid(project):
    """スロットデータを日付別・時間別のグリッドに変換する"""
    slots = project["slots"]
    interval = project.get("interval_minutes", 10)
    slots_per_hour = 60 // interval

    # {day_key: {slot_index: value}} の形式に変換
    days = {}
    for slot in slots:
        jst = utc_to_jst(slot["time_utc"])
        day_key = jst.strftime("%m/%d")
        if day_key not in days:
            days[day_key] = {}
        slot_index = jst.hour * slots_per_hour + jst.minute // interval
        days[day_key][slot_index] = slot

    return days, interval, slots_per_hour


def render_ascii(data, metric):
    blocks = " ░▒▓█"

    for project in data["projects"]:
        ns = project["namespace"]
        slots = project["slots"]
        if not slots:
            continue

        values = [s[metric] for s in slots]
        max_val = max(values) if values else 1

        days, interval, slots_per_hour = build_grid(project)

        for day_key, hour_map in days.items():
            print(f"\n[ {ns} ] {day_key} metric={metric}")

            # 時間軸ヘッダー
            print("       ", end="")
            for h in range(24):
                print(f"{h:>3}", end="")
            print()

            # 各10分スロット行
            for m_idx in range(slots_per_hour):
                minute = m_idx * interval
                print(f"  :{minute:02d}  ", end="")
                for h in range(24):
                    slot_index = h * slots_per_hour + m_idx
                    slot = hour_map.get(slot_index)
                    if slot is None:
                        print("  .", end="")
                    else:
                        val = slot[metric]
                        level = min(4, int(val / max(max_val, 1) * 4) + 1)
                        print(f"  {blocks[level]}", end="")
                print()

        print()


def render_color(data, metric):
    from rich.console import Console
    from rich.text import Text

    console = Console()

    # GitHubの草風パレット
    palette = [
        (22, 27, 34),     # 背景（ほぼ黒）
        (14, 68, 41),     # 薄緑
        (0, 109, 50),     # 緑
        (38, 166, 65),    # 明るい緑
        (57, 211, 83),    # 最も明るい緑
    ]

    for project in data["projects"]:
        ns = project["namespace"]
        slots = project["slots"]
        if not slots:
            continue

        values = [s[metric] for s in slots]
        max_val = max(values) if values else 1

        days, interval, slots_per_hour = build_grid(project)

        for day_key, hour_map in days.items():
            console.print(f"\n[bold][ {ns} ][/bold] {day_key}  metric={metric}")

            # 時間軸ヘッダー
            header = Text("       ")
            for h in range(24):
                header.append(f"{h:>3}", style="dim")
            console.print(header)

            # 各10分スロット行
            for m_idx in range(slots_per_hour):
                minute = m_idx * interval
                line = Text(f"  :{minute:02d}  ")
                for h in range(24):
                    slot_index = h * slots_per_hour + m_idx
                    slot = hour_map.get(slot_index)
                    if slot is None:
                        r, g, b = palette[0]
                    else:
                        val = slot[metric]
                        level = min(4, int(val / max(max_val, 1) * 4) + 1)
                        r, g, b = palette[level]
                    line.append(" ██", style=f"rgb({r},{g},{b})")
                console.print(line)

            # 凡例
            legend = Text("        ")
            legend.append("少 ", style="dim")
            for r, g, b in palette:
                legend.append("██", style=f"rgb({r},{g},{b})")
            legend.append(" 多", style="dim")
            console.print(legend)

        console.print()


def main():
    args = parse_args()

    data = load_data(args.file)

    if not data.get("projects"):
        print("該当期間にイベントが見つかりませんでした")
        return

    if args.color:
        render_color(data, args.metric)
    else:
        render_ascii(data, args.metric)


if __name__ == "__main__":
    main()

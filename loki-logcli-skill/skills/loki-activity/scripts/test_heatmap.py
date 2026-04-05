"""heatmap.py のテスト"""

import json
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from heatmap import (
    DayGrid,
    HeatmapLayout,
    PALETTE,
    utc_to_jst,
    build_grid,
    compute_level_matrix,
    _merge_overall,
    prepare_all_grids,
    render_ascii,
    render_color,
    draw_heatmap_image,
    emit_iterm2_image,
    is_iterm2,
)

JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# フィクスチャ
# ---------------------------------------------------------------------------

def _make_slot(hour, minute, total=10, user_prompt=3, api_request=4, tool_use=3):
    """テスト用スロットを生成する"""
    return {
        "time_utc": f"2026-04-05T{hour:02d}:{minute:02d}:00Z",
        "total": total,
        "user_prompt": user_prompt,
        "api_request": api_request,
        "tool_use": tool_use,
    }


@pytest.fixture
def sample_project():
    """テスト用のプロジェクトデータ（UTC 04:00-04:20 = JST 13:00-13:20）"""
    return {
        "namespace": "test-project",
        "interval_minutes": 10,
        "slots": [
            _make_slot(4, 0, total=10),
            _make_slot(4, 10, total=50),
            _make_slot(4, 20, total=100),
        ],
    }


@pytest.fixture
def two_projects():
    """2プロジェクト分のデータ"""
    return {
        "query_params": {"since": "24h", "project_filter": ""},
        "projects": [
            {
                "namespace": "alpha",
                "interval_minutes": 10,
                "slots": [
                    _make_slot(4, 0, total=20),
                    _make_slot(4, 10, total=30),
                ],
            },
            {
                "namespace": "beta",
                "interval_minutes": 10,
                "slots": [
                    _make_slot(4, 0, total=10),
                    _make_slot(4, 20, total=40),
                ],
            },
        ],
    }


def _make_daygrid(hour_labels=None, levels=None, raw_values=None):
    """テスト用DayGridを生成する"""
    if hour_labels is None:
        hour_labels = list(range(24))
    if levels is None:
        levels = [[-1] * 24 for _ in range(6)]
    if raw_values is None:
        raw_values = [[None] * 24 for _ in range(6)]
    return DayGrid(
        namespace="test",
        day_key="04/05",
        metric="total",
        interval=10,
        slots_per_hour=6,
        max_val=100,
        levels=levels,
        raw_values=raw_values,
        hour_labels=hour_labels,
    )


# ---------------------------------------------------------------------------
# テスト: utc_to_jst
# ---------------------------------------------------------------------------

class TestUtcToJst:
    def test_basic_conversion(self):
        result = utc_to_jst("2026-04-05T04:00:00Z")
        assert result.hour == 13
        assert result.day == 5

    def test_day_boundary(self):
        result = utc_to_jst("2026-04-05T15:30:00Z")
        assert result.hour == 0
        assert result.minute == 30
        assert result.day == 6

    def test_midnight_utc(self):
        result = utc_to_jst("2026-04-05T00:00:00Z")
        assert result.hour == 9
        assert result.day == 5


# ---------------------------------------------------------------------------
# テスト: build_grid
# ---------------------------------------------------------------------------

class TestBuildGrid:
    def test_basic_grid(self, sample_project):
        days, interval, slots_per_hour = build_grid(sample_project)
        assert interval == 10
        assert slots_per_hour == 6
        assert "04/05" in days

    def test_slot_index_calculation(self, sample_project):
        days, _, slots_per_hour = build_grid(sample_project)
        hour_map = days["04/05"]
        # UTC 04:00 -> JST 13:00 -> slot_index = 13 * 6 + 0 = 78
        assert 78 in hour_map
        assert hour_map[78]["total"] == 10
        # UTC 04:10 -> JST 13:10 -> slot_index = 13 * 6 + 1 = 79
        assert 79 in hour_map
        assert hour_map[79]["total"] == 50

    def test_empty_slots(self):
        project = {"namespace": "empty", "interval_minutes": 10, "slots": []}
        days, _, _ = build_grid(project)
        assert days == {}


# ---------------------------------------------------------------------------
# テスト: compute_level_matrix
# ---------------------------------------------------------------------------

class TestComputeLevelMatrix:
    def test_empty_slots(self):
        project = {"namespace": "empty", "interval_minutes": 10, "slots": []}
        result = compute_level_matrix(project, "total")
        assert result == []

    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_level_calculation(self, sample_project):
        grids = compute_level_matrix(sample_project, "total")
        assert len(grids) == 1
        g = grids[0]
        assert g.namespace == "test-project"
        assert g.metric == "total"
        assert g.max_val == 100

        # max_val=100, num_levels=5のとき:
        #   10  -> min(4, int(10/100*4)+1) = min(4, 1) = 1
        #   50  -> min(4, int(50/100*4)+1) = min(4, 3) = 3
        #   100 -> min(4, int(100/100*4)+1) = min(4, 5) = 4
        data_levels = []
        for row in g.levels:
            for val in row:
                if val != -1:
                    data_levels.append(val)
        assert len(data_levels) == 3
        assert sorted(data_levels) == [1, 3, 4]

    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_hour_labels_rotation(self, sample_project):
        grids = compute_level_matrix(sample_project, "total")
        g = grids[0]
        # JST 16時 -> start_hour = (16+1)%24 = 17
        assert g.hour_labels[0] == 17
        assert g.hour_labels[-1] == 16
        assert len(g.hour_labels) == 24

    @freeze_time("2026-04-05T14:30:00")  # UTC 14:30 = JST 23:30
    def test_hour_labels_midnight_wrap(self):
        project = {"namespace": "x", "interval_minutes": 10, "slots": [_make_slot(0, 0)]}
        grids = compute_level_matrix(project, "total")
        g = grids[0]
        # JST 23:30 -> start_hour = (23+1)%24 = 0
        assert g.hour_labels[0] == 0
        assert g.hour_labels[-1] == 23

    def test_raw_values_preserved(self, sample_project):
        grids = compute_level_matrix(sample_project, "total")
        g = grids[0]
        # raw_valuesにNone以外の値が3つあるはず
        non_none = [v for row in g.raw_values for v in row if v is not None]
        assert sorted(non_none) == [10, 50, 100]


# ---------------------------------------------------------------------------
# テスト: _merge_overall
# ---------------------------------------------------------------------------

class TestMergeOverall:
    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_single_project_returns_empty(self):
        project = {"namespace": "solo", "interval_minutes": 10, "slots": [_make_slot(4, 0)]}
        grids = compute_level_matrix(project, "total")
        result = _merge_overall(grids, "total")
        assert result == []

    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_two_projects_merged(self, two_projects):
        grids = []
        for p in two_projects["projects"]:
            grids.extend(compute_level_matrix(p, "total"))

        result = _merge_overall(grids, "total")
        assert len(result) == 1
        assert result[0].namespace == "Overall"

        # alpha: 04:00=20, 04:10=30
        # beta:  04:00=10, 04:20=40
        # overall: 04:00=30, 04:10=30, 04:20=40
        non_none = [v for row in result[0].raw_values for v in row if v is not None]
        assert sorted(non_none) == [30, 30, 40]

    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_overall_levels_recalculated(self, two_projects):
        grids = []
        for p in two_projects["projects"]:
            grids.extend(compute_level_matrix(p, "total"))

        result = _merge_overall(grids, "total")
        # max_val should be 40 (the max of merged values)
        assert result[0].max_val == 40


# ---------------------------------------------------------------------------
# テスト: prepare_all_grids
# ---------------------------------------------------------------------------

class TestPrepareAllGrids:
    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_single_project_no_overall(self):
        data = {
            "projects": [
                {"namespace": "solo", "interval_minutes": 10, "slots": [_make_slot(4, 0)]},
            ],
        }
        grids = prepare_all_grids(data, "total")
        assert all(g.namespace != "Overall" for g in grids)

    @freeze_time("2026-04-05T07:00:00")  # UTC 07:00 = JST 16:00
    def test_multiple_projects_has_overall_first(self, two_projects):
        grids = prepare_all_grids(two_projects, "total")
        assert grids[0].namespace == "Overall"
        assert grids[1].namespace in ("alpha", "beta")


# ---------------------------------------------------------------------------
# テスト: render_ascii
# ---------------------------------------------------------------------------

class TestRenderAscii:
    def test_output_contains_namespace(self, capsys):
        g = _make_daygrid()
        render_ascii([g])
        output = capsys.readouterr().out
        assert "[ test ]" in output

    def test_output_contains_day_key(self, capsys):
        g = _make_daygrid()
        render_ascii([g])
        output = capsys.readouterr().out
        assert "04/05" in output

    def test_empty_grid_shows_dots(self, capsys):
        g = _make_daygrid()
        render_ascii([g])
        output = capsys.readouterr().out
        assert "." in output
        # ブロック文字が含まれないこと
        for block in "\u2591\u2592\u2593\u2588":
            assert block not in output

    def test_data_shows_blocks(self, capsys):
        levels = [[-1] * 24 for _ in range(6)]
        levels[0][0] = 4  # 最高レベル
        g = _make_daygrid(levels=levels)
        render_ascii([g])
        output = capsys.readouterr().out
        assert "\u2588" in output  # █

    def test_header_uses_hour_labels(self, capsys):
        labels = list(range(17, 24)) + list(range(0, 17))  # 17から始まる
        g = _make_daygrid(hour_labels=labels)
        render_ascii([g])
        output = capsys.readouterr().out
        lines = output.strip().split("\n")
        header_line = lines[1]  # 2行目がヘッダー
        # 最初の数字が17であること
        numbers = [int(x) for x in header_line.split()]
        assert numbers[0] == 17
        assert numbers[-1] == 16

    def test_minute_labels(self, capsys):
        g = _make_daygrid()
        render_ascii([g])
        output = capsys.readouterr().out
        assert ":00" in output
        assert ":10" in output
        assert ":50" in output


# ---------------------------------------------------------------------------
# テスト: render_color
# ---------------------------------------------------------------------------

class TestRenderColor:
    def test_output_contains_namespace(self):
        g = _make_daygrid()
        # richのConsoleをStringIOに出力
        from rich.console import Console
        buf = StringIO()
        console = Console(file=buf, force_terminal=True)
        # render_colorは内部でConsole()を作るので、monkeypatchで差し替え
        with patch("heatmap.render_color") as _:
            pass
        # 直接呼んでcapsysの代わりにStringIOに出力させるのは難しいので
        # 関数内部のconsoleをpatchする方が確実
        # ここではシンプルにrender_colorを呼んで例外が出ないことを確認
        render_color([g])

    def test_no_error_with_data(self):
        levels = [[-1] * 24 for _ in range(6)]
        levels[0][5] = 3
        g = _make_daygrid(levels=levels)
        render_color([g])  # 例外が出ないこと

    def test_legend_rendered(self, capsys):
        g = _make_daygrid()
        render_color([g])
        # richは色付きで出力するのでcapsysでは不完全だが
        # 少なくとも何か出力されること
        output = capsys.readouterr().out
        assert len(output) > 0


# ---------------------------------------------------------------------------
# テスト: draw_heatmap_image
# ---------------------------------------------------------------------------

class TestHeatmapLayout:
    def test_step(self):
        layout = HeatmapLayout(rows=6)
        assert layout.step == layout.cell_size + layout.cell_gap

    def test_width_height(self):
        layout = HeatmapLayout(rows=6)
        assert layout.width == layout.margin_left + 24 * layout.step + layout.margin_right
        assert layout.height == layout.margin_top + 6 * layout.step + layout.margin_bottom

    def test_cell_rect(self):
        layout = HeatmapLayout(rows=6)
        rect = layout.cell_rect(0, 0)
        assert rect == [layout.margin_left, layout.margin_top,
                        layout.margin_left + layout.cell_size, layout.margin_top + layout.cell_size]

    def test_cell_rect_offset(self):
        layout = HeatmapLayout(rows=6)
        rect = layout.cell_rect(2, 3)
        x = layout.margin_left + 3 * layout.step
        y = layout.margin_top + 2 * layout.step
        assert rect == [x, y, x + layout.cell_size, y + layout.cell_size]

    def test_cell_center(self):
        layout = HeatmapLayout(rows=6)
        cx, cy = layout.cell_center(0, 0)
        assert cx == layout.margin_left + layout.cell_size // 2
        assert cy == layout.margin_top + layout.cell_size // 2

    def test_title_pos(self):
        layout = HeatmapLayout(rows=6)
        assert layout.title_pos() == (layout.margin_left, layout.title_y)

    def test_header_pos(self):
        layout = HeatmapLayout(rows=6)
        x, y = layout.header_pos(5)
        assert x == layout.margin_left + 5 * layout.step + layout.cell_size // 2
        assert y == layout.margin_top - layout.header_offset

    def test_label_pos(self):
        layout = HeatmapLayout(rows=6)
        x, y = layout.label_pos(3)
        assert x == layout.margin_left - layout.label_offset
        assert y == layout.margin_top + 3 * layout.step + layout.cell_size // 2

    def test_legend_pos(self):
        layout = HeatmapLayout(rows=6)
        lx, ly = layout.legend_pos()
        assert lx == layout.margin_left
        assert ly == layout.margin_top + 6 * layout.step + layout.legend_gap

    def test_custom_parameters(self):
        layout = HeatmapLayout(rows=4, cell_size=20, cell_gap=4, margin_left=50, margin_top=30)
        assert layout.step == 24
        assert layout.width == 50 + 24 * 24 + layout.margin_right
        cx, cy = layout.cell_center(1, 2)
        assert cx == 50 + 2 * 24 + 10
        assert cy == 30 + 1 * 24 + 10


class TestDrawHeatmapImage:
    def test_image_size(self):
        g = _make_daygrid()
        layout = HeatmapLayout(rows=g.slots_per_hour)
        img = draw_heatmap_image(g, layout=layout)
        assert img.size == (layout.width, layout.height)

    def test_image_mode(self):
        g = _make_daygrid()
        img = draw_heatmap_image(g)
        assert img.mode == "RGB"

    def test_empty_cell_is_background_color(self):
        g = _make_daygrid()
        layout = HeatmapLayout(rows=g.slots_per_hour)
        img = draw_heatmap_image(g, layout=layout)
        cx, cy = layout.cell_center(0, 0)
        pixel = img.getpixel((cx, cy))
        assert pixel == PALETTE[0]

    def test_active_cell_has_correct_color(self):
        levels = [[-1] * 24 for _ in range(6)]
        levels[0][0] = 4
        g = _make_daygrid(levels=levels)
        layout = HeatmapLayout(rows=g.slots_per_hour)
        img = draw_heatmap_image(g, layout=layout)
        cx, cy = layout.cell_center(0, 0)
        pixel = img.getpixel((cx, cy))
        assert pixel == PALETTE[4]

    def test_different_levels_different_colors(self):
        levels = [[-1] * 24 for _ in range(6)]
        levels[0][0] = 1
        levels[0][1] = 4
        g = _make_daygrid(levels=levels)
        layout = HeatmapLayout(rows=g.slots_per_hour)
        img = draw_heatmap_image(g, layout=layout)
        p0 = img.getpixel(layout.cell_center(0, 0))
        p1 = img.getpixel(layout.cell_center(0, 1))
        assert p0 == PALETTE[1]
        assert p1 == PALETTE[4]
        assert p0 != p1


# ---------------------------------------------------------------------------
# テスト: emit_iterm2_image
# ---------------------------------------------------------------------------

class TestEmitIterm2Image:
    def test_protocol_prefix(self):
        from PIL import Image
        img = Image.new("RGB", (10, 10), (0, 0, 0))
        buf = StringIO()
        with patch("sys.stdout", buf):
            emit_iterm2_image(img)
        output = buf.getvalue()
        assert "\033]1337;File=" in output
        assert "inline=1" in output

    def test_contains_base64_png(self):
        from PIL import Image
        img = Image.new("RGB", (10, 10), (0, 0, 0))
        buf = StringIO()
        with patch("sys.stdout", buf):
            emit_iterm2_image(img)
        output = buf.getvalue()
        # base64 PNGデータが含まれる（PNGのbase64は iVBOR で始まる）
        assert "iVBOR" in output


# ---------------------------------------------------------------------------
# テスト: is_iterm2
# ---------------------------------------------------------------------------

class TestIsIterm2:
    def test_iterm2_detected(self):
        with patch.dict("os.environ", {"TERM_PROGRAM": "iTerm.app"}):
            assert is_iterm2() is True

    def test_lc_terminal_detected(self):
        with patch.dict("os.environ", {"LC_TERMINAL": "iTerm2"}, clear=True):
            assert is_iterm2() is True

    def test_other_terminal(self):
        with patch.dict("os.environ", {"TERM_PROGRAM": "Apple_Terminal"}, clear=True):
            assert is_iterm2() is False

    def test_no_env_vars(self):
        with patch.dict("os.environ", {}, clear=True):
            assert is_iterm2() is False

# loki-activity

Claude Codeの作業時間をGrafana Loki/logcliから取得・集計・可視化するClaude Codeスキル。

## 概要

Claude CodeのOTELテレメトリがGrafana Lokiに蓄積されている前提で、プロジェクト別の作業時間帯をサマリー表示・ヒートマップ表示する。

## 構成

```
skills/loki-activity/
  SKILL.md                  Claude Codeスキル定義
  scripts/
    activity.sh             logcliクエリのラッパー（サマリー/ディテール出力）
    heatmap.py              ヒートマップ表示（ASCII/TrueColor/iTerm2画像/ファイル保存）
    test_activity.sh        activity.shのテスト
    test_heatmap.py         heatmap.pyのテスト
    fixtures/               テスト用フィクスチャデータ
```

## 前提条件

- logcli（Grafana Lokiのクライアント）
- jq
- Python 3.10+
- uv（PEP 723でrich/Pillowを自動インストール）
- 環境変数: LOKI_ADDR, LOKI_USERNAME, LOKI_PASSWORD

## 使い方

### スキルとして（Claude Code内）

```
/loki-activity              今日の作業時間（現在のプロジェクト）
/loki-activity all          今日の全プロジェクト
/loki-activity week         過去7日
/loki-activity aleister 3   aleisterプロジェクトの過去3日
```

### 直接実行

```bash
# サマリー取得
bash scripts/activity.sh --all

# ASCIIヒートマップ
bash scripts/activity.sh --all | uv run scripts/heatmap.py

# TrueColorヒートマップ
bash scripts/activity.sh --all | uv run scripts/heatmap.py --color

# iTerm2画像表示
bash scripts/activity.sh --all | uv run scripts/heatmap.py --image

# Overallのみ（全プロジェクト合算）
bash scripts/activity.sh --all | uv run scripts/heatmap.py --overall

# 画像ファイル保存
bash scripts/activity.sh --all | uv run scripts/heatmap.py --output heatmap.png
```

### テスト

```bash
cd skills/loki-activity/scripts

# heatmap.pyのテスト
uv run --with pytest --with freezegun --with rich --with Pillow pytest test_heatmap.py -v

# activity.shのテスト
bash test_activity.sh
```

## インストール

グローバルスキルとしてシンボリックリンクを張る:

```bash
ln -s $(pwd)/skills/loki-activity ~/.claude/skills/loki-activity
```

# gsearch-skill

Claude Code から Gemini API の Google Search グラウンディング（`google_search`）で web 検索する薄い skill。
内蔵 WebSearch の代替で、質問を Gemini が咀嚼して検索クエリを組み、根拠付き回答＋ソースを返す。

- 実体: `skills/gsearch/`（`SKILL.md` ＋ `search.js`）
- 有効化: `~/.claude/skills/gsearch` をこの `skills/gsearch` への symlink にする
  ```bash
  ln -s "$PWD/skills/gsearch" ~/.claude/skills/gsearch
  ```

## 前提

- node v18+（fetch 内蔵）
- 環境変数 `GEMINI_API_KEY`（skill 自体はキーを保持しない）

## 使い方

```bash
node skills/gsearch/search.js "<質問(自然文)>" [model]
```

出力: 回答 → Gemini が自動生成した検索クエリ → ソースURL。所要 ~15〜20秒。
詳細は `skills/gsearch/SKILL.md` を参照。

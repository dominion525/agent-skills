---
name: jetdb-cli
description: >
  Microsoft Access (.mdb / .accdb) データベースを読み取り、テーブル一覧、
  スキーマ表示、CSV エクスポート、SQLite / PostgreSQL / MySQL / Access 向け
  DDL 生成、VBA ソース抽出、保存済みクエリの SQL 表示、フォーム / レポートの
  デザインプロパティ（RecordSource、ControlSource、イベントハンドラ等）の
  検査を行う。Access から他 RDBMS への移行、レガシー MDB / ACCDB
  ファイルからのデータ抽出、Jet3 (Access 97) から ACE17 (Access 2019) までの
  スキーマ調査、パスワード保護されたデータベースからの VBA モジュール・
  フォーム / レポート定義の復元時に使用する。
allowed-tools: Bash, Read
---

# jetdb CLI

Microsoft Access (`.mdb` / `.accdb`) データベース向けの読み取り専用 CLI。単一 Rust バイナリ、ランタイム依存なし。

```
cargo install jetdb-cli
```

## 運用ルール

```
jetdb [--password <PASS>] <COMMAND> [OPTIONS] <FILE> [ARGS]
```

- `--password` は **グローバル**オプション。サブコマンドの前後どちらにも指定可能。
- オブジェクト名（テーブル、クエリ、VBA モジュール、フォーム、レポート、`prop` の対象）は**大文字小文字を含む完全一致**で照合する。Access の名前にはスペース、マルチバイト文字、大文字小文字違いの版が頻出するため、引数は常に引用する。名前は対応する `list` コマンドの出力を真とする。決して推測しない。
- 成功時の出力は stdout、警告と実行時エラーは stderr に `jetdb: ...` 形式で出す（警告は `jetdb: warning: ...`）。
- 終了コード: 成功 → 0、実行時エラー → 1、CLI 引数エラー → 2（Clap 既定、stderr が `error:` で始まる）。
- `list` 系コマンドはデータなしの場合 → exit 0 / 空 stdout（エラー扱いではない）。
- `export` と `vba show` は全結果を stdout にストリーム出力する。**大きい出力は必ずファイルにリダイレクトする** (`> out.csv`) のが原則。エージェントに生のストリームを読ませない。
- `export` 後は stderr に `jetdb: warning: N row(s) skipped` が出ていないか確認する。終了コードは 0 のままでも CSV が不完全。
- テキストデコード: Jet3 (Access 97) は Latin-1、Jet4 以降と ACE は UTF-16LE で読み出し、いずれも UTF-8 で出力する。Latin-1 以外の環境（例: 日本語 CP932）で作成された Jet3 データベースは文字化けする可能性がある — 元ファイル側の制約であって変換側の制約ではない。

## コマンド

### ver — エンジンバージョン

```
jetdb ver <FILE>              # 短縮トークン: JET3 | JET4 | ACE12 .. ACE17
jetdb ver -l <FILE>           # 詳細形式、例: "Jet4 (Access 2000/2003)"
```

### tables — テーブル一覧

```
jetdb tables <FILE>           # ユーザーテーブル、1行1件、ソート済み
jetdb tables -s <FILE>        # システムテーブル (MSys*) も含める
jetdb tables -T <FILE>        # 種別名 (table / systable) をタブ区切りで前置
jetdb tables -t <FILE>        # 種別番号をタブ区切りで前置
```

`-t` と `-T` は排他。

出力例:

```
$ jetdb tables -s -T data.mdb
systable	MSysACEs
systable	MSysObjects
table	Customers
table	Orders
```

### schema — テーブル構造と DDL

```
jetdb schema <FILE>                      # 全ユーザーテーブル、人間可読
jetdb schema <FILE> -T <TABLE>           # 単一テーブル
jetdb schema <FILE> --ddl sqlite         # sqlite | postgres | mysql | access
jetdb schema <FILE> --no-indexes --no-relations
```

`--no-indexes` と `--no-relations` は人間可読 / DDL 両方の出力に適用される。人間可読形式では `Columns:` / `Indexes:` / `Relationships:` セクションを出力。DDL 形式では `CREATE TABLE`、`CREATE INDEX`、`ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` を生成する。

出力例（人間可読形式）:

```
Table: Customers

  Columns:
    ID    Long         NOT NULL AUTO
    Name  Text(100)
    Email Text(200)

  Indexes:
    PrimaryKey  [ID ASC]  UNIQUE REQUIRED
```

### export — CSV エクスポート

```
jetdb export <FILE> <TABLE>                              # RFC 4180 CSV を stdout へ
jetdb export <FILE> <TABLE> -H                           # ヘッダー行を省略
jetdb export <FILE> <TABLE> -d $'\t'                     # タブ区切り（リテラルの "\t" は不可）
jetdb export <FILE> <TABLE> -D "%Y-%m-%d"                # 日付フォーマット (strftime)
jetdb export <FILE> <TABLE> -T "%Y-%m-%dT%H:%M:%S"       # 日時フォーマット
jetdb export <FILE> <TABLE> -b hex                       # バイナリモード (既定: hex)
jetdb export <FILE> <TABLE> -0 NULL                      # NULL の表現文字列 (既定: 空文字列)
jetdb export <FILE> <TABLE> -B                           # 真偽値を TRUE/FALSE (既定: 1/0)
jetdb export <FILE> <TABLE> -s                           # レプリケーション列も含める
```

- `-d/--delimiter` は文字列を受け取るが**先頭1文字のみ**を使う（複数文字なら警告）。bash/zsh のタブは `-d $'\t'`。`"\t"` はバックスラッシュ + t のリテラル。
- `-b` モード（既定 `hex`）:
  - `strip` — バイナリを完全に捨てる（空セル）
  - `raw` — UTF-8 lossy デコード、区切り / クオート / 改行を含むときのみ CSV エスケープ
  - `octal` — 1 バイトを `\NNN` で
  - `hex` — 1 バイトを小文字16進で
- テキスト値と GUID は常にクオート、数値はクオートなし。
- テーブル全体をメモリに読み込み stdout にストリーム出力する。大きいテーブルはファイルにリダイレクトしてから `wc -l` / `head` で確認する。

出力例:

```
ID,Name,Email,Active
1,"Alice","alice@example.com",1
2,"Bob","bob@example.com",0
```

### queries — 保存済みクエリ

```
jetdb queries list <FILE>                  # スペース区切り、ソート済み
jetdb queries list -1 <FILE>               # 1行1件
jetdb queries list -d , <FILE>             # 区切り文字をカスタム指定（先頭1文字のみ）
jetdb queries show <FILE> <QUERY_NAME>     # 再構成した SQL を出力
```

`-1` と `-d` は排他。

### vba — VBA モジュール

```
jetdb vba list <FILE>                      # スペース区切り、ソート済み
jetdb vba list -1 <FILE>                   # 1行1件
jetdb vba list -d , <FILE>                 # 区切り文字をカスタム指定
jetdb vba show <FILE> <MODULE_NAME>        # ソース全文 (UTF-8) を出力
```

`-1` と `-d` は排他。

### form — フォーム / レポート

Jet4 / ACE 専用。Access 97 (Jet3) は `form` が解析する `MSysAccessStorage` 形式のフォーム / レポート設計データを持たない。

```
jetdb form list <FILE>                     # フォーム + レポート、スペース区切り、ソート済み
jetdb form list -1 <FILE>                  # 1行1件
jetdb form list -d , <FILE>                # 区切り文字をカスタム指定
jetdb form list --forms-only <FILE>        # フォームのみ
jetdb form list --reports-only <FILE>      # レポートのみ
jetdb form dump <FILE> <NAME>              # 既定の Blob ストリームを stdout へ — ファイルへリダイレクトすること
jetdb form dump <FILE> <NAME> -s typeinfo  # ストリーム: blob (既定) | typeinfo | propdata | blobdelta
jetdb form controls <FILE> <NAME>          # name<TAB>type<TAB>index 形式、1行1件
jetdb form props <FILE> <NAME>             # フォーム / コントロールのプロパティを整形出力
```

- `--forms-only` と `--reports-only` は排他、`-1` と `-d` も排他。
- `form dump` は**生バイナリ**を stdout に書き出す。必ずリダイレクト (`> form.blob`) し、会話に流さない。
- `form controls`: 既知の制御コードは型名 (`TextBox`、`CommandButton`、`Label` 等) に解決される。未知コードは `0xNNNN` で表示。
- `form props`: プロパティは Blob ペイロードから取得する (`RecordSource`、`ControlSource`、`Filter`、`Caption`、`FontName`、`Format`、`OnClick` 等のイベントハンドラ等)。バイナリ値は `(N bytes)`、GUID は `{…}`、真偽値は `yes`/`no` で表示。コントロール型名は TypeInfo が利用可能なら使用し、それ以外は型を `0x0000` として表示する。

出力例 (`form controls`):

```
$ jetdb form controls data.accdb F_Customers
Txt_Name	TextBox	1
Btn_Save	CommandButton	2
Lbl_Title	Label	3
```

出力例 (`form props`):

```
$ jetdb form props data.accdb F_Customers
Form: F_Customers

  Form Properties:
    RecordSource  SELECT * FROM Customers ORDER BY ID;
    Filter        ([Active] = True)
    FontName      MS UI Gothic

  Control: Txt_Name (TextBox)
    Name           Txt_Name
    ControlSource  Name
    FontName       Meiryo UI
```

### prop — オブジェクトの LvProp

```
jetdb prop <FILE> <OBJECT_NAME>
```

LvProp 値を Table Properties、列ごとのブロック、Additional Properties にグループ化して表示する。

注意: 指定したオブジェクト名が存在しない、または LvProp データを持たない場合、`prop` は exit 0 / 空 stdout で終了する — 「not found」エラーは発生しない。先に `jetdb tables`（または対応する `list` コマンド）で名前を確認する。

## 暗号化データベース

`.mdb` (Jet3 / Jet4) は Jet RC4 難読化を jetdb が透過的に解除する — パスワード不要。
`.accdb` (ACE12+) はパスワード保護されている場合がある:

```
jetdb --password "secret" tables protected.accdb
# 等価（--password はグローバル）
jetdb tables protected.accdb --password "secret"
```

## ワークフローパターン

### 未知のデータベースを調査する

```
jetdb ver data.mdb
jetdb tables -s data.mdb
jetdb schema data.mdb
```

### 分析用にテーブルをエクスポート（必ずファイルへ）

```
jetdb tables data.mdb
jetdb schema data.mdb -T Customers
jetdb export data.mdb Customers > customers.csv
head -n 5 customers.csv
wc -l customers.csv
```

### 移行先 RDBMS の DDL を生成

```
jetdb schema data.mdb --ddl postgres > schema.sql
```

### 全 VBA モジュールを個別ファイルに抽出

```
jetdb vba list -1 data.mdb | while IFS= read -r mod; do
  jetdb vba show data.mdb "$mod" > "${mod}.bas"
done
```

### 全保存済みクエリを 1 ファイルにまとめる

```
jetdb queries list -1 data.mdb | while IFS= read -r q; do
  printf '=== %s ===\n' "$q"
  jetdb queries show data.mdb "$q"
done > queries.sql
```

### フォーム / レポート設計を調査

```
jetdb form list data.accdb
jetdb form props data.accdb F_Main
jetdb form controls data.accdb F_Main
```

## エラー動作

- ファイルが見つからない / 読み取り不可 → exit 1
- 不正なファイルフォーマット → exit 1
- パスワード必須だが未指定 → exit 1、stderr: `jetdb: this database is password-protected`
- パスワードが不正 → exit 1、stderr: `jetdb: invalid password`
- `*show` / `form dump|controls|props` で未知のオブジェクト名 → exit 1
- `prop` で未知のオブジェクト名または LvProp なし → exit 0、空 stdout (無音)
- `list` 系コマンドでデータなし → exit 0、空 stdout
- 部分的な export → exit 0 で stderr に `jetdb: warning: N row(s) skipped` — CSV は不完全として扱う
- CLI 引数不正 → exit 2、stderr が `error:` で始まる

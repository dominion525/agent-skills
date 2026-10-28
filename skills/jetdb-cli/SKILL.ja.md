---
name: jetdb-cli
description: >
  jetdb CLI 0.4 で Microsoft Access (.mdb / .accdb) データベースを読み取る。テーブル一覧、スキーマ表示、CSV エクスポート（複数値列・添付ファイル列を含む）、SQLite / PostgreSQL / MySQL / Access 向け DDL 生成、VBA ソース抽出、保存済みクエリの SQL 表示、オブジェクトのプロパティとフォーム / レポートのデザイン（セクション、コントロール、RecordSource、ControlSource、イベントハンドラ）の検査、名前付きマクロ・フォーム / レポートの埋め込みマクロ・テーブルのデータマクロの SaveAsText テキストまたは XML での表示を行う。Access から他 RDBMS への移行、レガシー MDB / ACCDB ファイルからのデータ抽出、Jet3 (Access 97) から ACE17 (Access 2019) までのデータベースの調査、パスワード保護された .accdb を含む VBA・クエリ・マクロ・フォーム / レポート定義の取り出しに使用する。
allowed-tools: Bash, Read
---

# jetdb CLI

Microsoft Access (`.mdb` / `.accdb`) データベース向けの読み取り専用 CLI、バージョン 0.4。単一 Rust バイナリ、ランタイム依存なし。

```
cargo install jetdb-cli
```

## 運用ルール

```
jetdb [--password <PASS>] <COMMAND> [OPTIONS] <FILE> [ARGS]
```

- `--password` は**グローバル**オプション。サブコマンドの前後どちらにも置ける。
- オブジェクト名（テーブル、クエリ、VBA モジュール、フォーム、レポート、マクロ、`prop` の対象）は**大文字小文字を含む完全一致**で照合する。Access の名前にはスペースやマルチバイト文字が多いため、常に引用する。名前は対応する `list` コマンド（または `tables`）の出力から取る。決して推測しない。
- 種類の違うオブジェクトが同じ名前を持つことがある（テーブル・フォーム・マクロがすべて `Customers`、フォームとレポートがともに `Shared` など）。このとき `prop`、`form dump|controls|props`、`macro embedded` は失敗して種類を列挙するので、`-t/--type` を付けて再実行する。
- 結果は stdout。エラーは stderr に `jetdb: <メッセージ>`、警告は `jetdb: warning: <メッセージ>` で出る。
- 終了コード: 成功 → 0、実行時エラー → 1、引数の誤り → 2（stderr は `error:` で始まる）。サブコマンドなしの `jetdb` は使い方を stderr に出して 2 で終わる。
- list 系コマンドは名前を 1 行に 1 つ、ソートして出す。データなし（クエリ・VBA・マクロがない）→ exit 0 / 空 stdout。エラーではない。
- `export`、`vba show`、`macro`、`form props` は出力が大きくなりうる。**大きい出力はファイルにリダイレクトし**（`> out.csv`）、ファイルを調べる。先頭を見るだけなら `head -n N` へのパイプは安全（パイプが閉じると jetdb は静かに終わる）。
- `form dump` は生のバイナリを書く。必ずファイルにリダイレクトし、バイト列を会話に流さない。
- 終了コードが 0 でも stderr の `jetdb: warning:` 行を確認する。特に `export` は `jetdb: warning: <TABLE>: N row(s) skipped due to parse errors` を出すことがあり、そのとき CSV は不完全。
- テキスト: Jet3 (Access 97) はデータベースのコードページ（1252、日本語なら 932 など）、Jet4 と ACE は UTF-16LE で読み、出力はすべて UTF-8。

## コマンド

### ver — エンジンバージョン

```
jetdb ver <FILE>              # JET3 | JET4 | ACE12 | ACE14 | ACE15 | ACE16 | ACE17
jetdb ver -l <FILE>           # 詳細形式
```

```
$ jetdb ver nwind.mdb
JET3
$ jetdb ver -l nwind.mdb
Jet3 (Access 97)
```

### tables — テーブル一覧

```
jetdb tables <FILE>           # ユーザーテーブル、1 行 1 つ、ソート済み
jetdb tables -s <FILE>        # SYSTEM / HIDDEN フラグのテーブル（MSys*、f_..._Data など）も含める
jetdb tables -T <FILE>        # 型名（table / systable）をタブ区切りで前置
jetdb tables -t <FILE>        # 型番号（どのテーブルも 1）をタブ区切りで前置
```

`-t` と `-T` は同時に指定できない。ユーザーテーブルとシステムテーブルを区別できるのは `-T` だけ。

```
$ jetdb tables jetdb-sample.accdb
tblCustomers
tblOrders
tblProducts
```

### schema — テーブル構造と DDL

```
jetdb schema <FILE>                      # 全ユーザーテーブル、人間向け形式
jetdb schema <FILE> -T <TABLE>           # 1 テーブルのみ
jetdb schema <FILE> --ddl postgres       # sqlite | postgres | mysql | access
jetdb schema <FILE> --no-indexes --no-relations
```

- 人間向け形式はテーブルごとに `Columns:`、`Indexes:`、`Relationships:` を出す。列はデザインビューの順、Text のサイズは文字数。`NOT NULL` は値要求の列、`AUTO` はオートナンバー、`CALC` は集計列（結果の型で表示）。
- DDL 形式は `CREATE TABLE`、`CREATE INDEX`、`ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` を出す。参照整合性のないリレーションシップは外部キーではなく `--` コメントで書く（Access の DDL では省く）。GUID のオートナンバー列には、方言にあれば GUID を生成する既定値が付く。
- `--no-indexes` / `--no-relations` は両形式に効く。
- `-T` のテーブルがない → exit 1、`jetdb: table not found: <NAME>`。

```
$ jetdb schema jetdb-sample.accdb -T tblOrders
Table: tblOrders

  Columns:
    OrderID     Long       AUTO
    CustomerID  Long       NOT NULL
    ProductID   Long       NOT NULL
    Quantity    Int        NOT NULL
    OrderDate   Timestamp  NOT NULL
    Shipped     Boolean

  Indexes:
    pkOrders  [OrderID ASC]  UNIQUE REQUIRED

  Relationships:
    fkOrdersCustomers  tblOrders.CustomerID -> tblCustomers.CustomerID
    fkOrdersProducts   tblOrders.ProductID -> tblProducts.ProductID
```

```
$ jetdb schema jetdb-sample.accdb --ddl postgres -T tblOrders
CREATE TABLE "tblOrders" (
    "OrderID" INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY,
    "CustomerID" INTEGER NOT NULL,
    ...
    PRIMARY KEY ("OrderID")
);

ALTER TABLE "tblOrders" ADD CONSTRAINT "fkOrdersCustomers"
    FOREIGN KEY ("CustomerID") REFERENCES "tblCustomers" ("CustomerID");
...
```

### export — CSV エクスポート

```
jetdb export <FILE> <TABLE>                         # RFC 4180 CSV を stdout へ
jetdb export <FILE> <TABLE> -H                      # ヘッダー行なし
jetdb export <FILE> <TABLE> -d $'\t'                # 区切り文字: ちょうど 1 文字（既定 ,）
jetdb export <FILE> <TABLE> -D "%d/%m/%Y"           # 時刻のない日付の形式（既定 %Y-%m-%d）
jetdb export <FILE> <TABLE> -T "%Y-%m-%dT%H:%M:%S"  # 時刻のある日付の形式（既定 "%Y-%m-%d %H:%M:%S"）
jetdb export <FILE> <TABLE> -b strip                # バイナリ: strip | raw | octal | hex（既定 hex）
jetdb export <FILE> <TABLE> -0 NULL                 # NULL の文字列（既定: 空）
jetdb export <FILE> <TABLE> -B                      # 真偽値を TRUE/FALSE で（既定 1/0）
jetdb export <FILE> <TABLE> -s                      # 隠し列（HIDDEN フラグ）も含める
jetdb export <FILE> <TABLE> --attachments <DIR>     # 添付ファイルを DIR の下に書き出す
```

- `-d` はちょうど 1 文字。空や 2 文字以上は exit 1 で失敗する: `jetdb: delimiter must be one character, got '\t'`。bash / zsh ではタブを `-d $'\t'` と書く。`"\t"` はバックスラッシュと `t`。
- 既定では Access が管理して隠している列を除く。`-s` で含める。システムテーブルは常に全列を出す。
- テキスト、GUID、拡張日付/時刻の値は常に引用する。その他の値は区切り文字・引用符・改行を含むときだけ引用する。
- 時刻を持たない日付/時刻の値は `-D`、それ以外は `-T`（strftime のサブセット）で書く。
- バイナリモード: `strip` 空フィールド、`raw` バイト列を lossy な UTF-8 で、`octal` 1 バイトごとに `\NNN`、`hex` 小文字 16 進。
- 複合列（Access 2007 以降）: 複数値 → 値を `;` で連結して 1 つの引用フィールドに、添付ファイル → ファイル名を `;` で連結、追加のみの長いテキストの履歴 → 数値（件数ではなく ID。最新のテキストは長いテキスト列そのものにある）。値がなければ空フィールド。
- `--attachments <DIR>` は各ファイルを `<DIR>/<番号>/<ファイル名>` に書き（名前中の `/` と `\` は `_` になる）、`<DIR>` からの相対パスをフィールドに入れる。
- 行は逐次出力されるので、大きなテーブルもメモリに収まる必要はない。ファイルにリダイレクトし、`wc -l` と stderr を確認する。

```
$ jetdb export jetdb-sample.accdb tblProducts
ProductID,ProductName,UnitPrice,Discontinued
1,"Coffee Beans 1kg",2400.0000,0
2,"Paper Filters (100)",380.0000,0
3,"Hand Grinder",6800.0000,1
...
```

```
$ jetdb export --attachments att complexDataTestV2010.accdb Table1
id,VersionHistory_F5F8918F-0A3F-4DA9-AE71-184EE5012880,memo-data,append-memo-data,multi-value-data,attach-data
"row1",1,,,,
"row2",2,"row2-memo","row2-memo","value1;value4","2/test_data.txt;2/test_data2.txt"
"row3",3,"row3-memo","row3-memo-again","value1;value2;value3;value4",
"row4",4,"row4-memo","row4-memo",,"4/test_data2.txt"
```

### queries — 保存済みクエリ

```
jetdb queries list <FILE>                  # 1 行 1 名、ソート済み
jetdb queries list -d "|" <FILE>           # 全名を 1 行に、文字列で連結
jetdb queries show <FILE> <QUERY_NAME>     # 復元した SQL
```

- `queries list`、`vba list`、`form list`、`macro list` 共通: `-d` は任意の文字列を取る。`-1` は互換のために受け付けるだけで何もしない。`-1` と `-d` の同時指定は引数エラー（exit 2）。
- MSysQueries の行が読めないとき、`queries show` は欠けているかもしれない SQL を出さずに失敗する（`jetdb: query <NAME> may be incomplete: rows of MSysQueries could not be read`）。

```
$ jetdb queries show jetdb-sample.accdb qryMonthlySales
SELECT Format(tblOrders.OrderDate, 'yyyy-mm') AS SalesMonth, tblCustomers.CustomerName, Sum(tblOrders.Quantity * tblProducts.UnitPrice) AS Total
FROM (tblOrders INNER JOIN tblCustomers ON tblOrders.CustomerID = tblCustomers.CustomerID) INNER JOIN tblProducts ON tblOrders.ProductID = tblProducts.ProductID
GROUP BY Format(tblOrders.OrderDate, 'yyyy-mm'), tblCustomers.CustomerName
ORDER BY Format(tblOrders.OrderDate, 'yyyy-mm'), tblCustomers.CustomerName;
```

### vba — VBA モジュール

```
jetdb vba list <FILE>                      # 1 行 1 名、ソート済み
jetdb vba list -d "|" <FILE>               # 1 行に、文字列で連結
jetdb vba show <FILE> <MODULE_NAME>        # ソース全文（UTF-8）
```

```
$ jetdb vba list -d "|" jetdb-sample.accdb
Form_frmOrders|modBilling
```

### prop — オブジェクトのプロパティ（LvProp）

```
jetdb prop <FILE> <OBJECT_NAME>
jetdb prop -t <TYPE> <FILE> <OBJECT_NAME>
```

- `-t/--type`: `table`、`query`、`form`、`report`、`macro`、`module`、`linkedtable`、`linkedodbctable`、`relationship`、`container`、`database`、`dbproperty`、`userinfo`。
- 出力: `Object: <NAME>` の後に、オブジェクト自身のプロパティを種類の語の見出し（`Table Properties:`、`Query Properties:`、`Macro Properties:`、`Linked Table Properties:` など。種類が不明なら `Object Properties:`）で出し、続けて `Column: <NAME>` と `Additional Properties:` のブロックを格納順に出す。
- テキスト値は二重引用符で囲み、`\\`、`\"`、`\r`、`\n`、`\t`、`\u{..}` でエスケープするので、1 プロパティは 1 行。バイナリは `(N bytes)`、GUID は `{...}`、真偽値は `yes`/`no`。
- オブジェクトがない → exit 1、`jetdb: object not found: <NAME>`（`--type` 付きなら `table not found: ...` など）。存在するがプロパティがない → exit 0 / 空 stdout。

```
$ jetdb prop jetdb-sample.accdb tblOrders
Object: tblOrders

  Table Properties:
    Description  "One row per ordered product"
    GUID         {1F1C571D-1956-447B-915D-E6177370C4F1}

  Column: CustomerID
    Required  yes
    GUID      {3FBE1C68-7833-413A-9E86-97EBF43A71CB}
...
```

```
$ jetdb prop nwind.mdb Customers
jetdb: objects of several types are named Customers: form, macro, table; choose one with --type
$ jetdb prop -t table nwind.mdb Customers
Object: Customers

  Table Properties:
    Description                 "Customers' names, addresses, and phone numbers."
...
```

### form — フォームとレポート

Access 2000 以降（Jet4 と ACE）を読む。Access 97 (Jet3) のフォームとレポートは読まない: `form list` は何も出さず、`form dump|controls|props`（と `macro embedded`）は `jetdb: the forms and reports of Access 97 are not read` で失敗する（exit 1）。

```
jetdb form list <FILE>                       # フォームとレポート、1 行 1 名、ソート済み
jetdb form list --forms-only <FILE>          # フォームのみ（--reports-only: レポートのみ）
jetdb form list -d "|" <FILE>                # 1 行に、文字列で連結
jetdb form controls <FILE> <NAME>            # セクションとコントロール: 名前<TAB>型<TAB>位置
jetdb form props <FILE> <NAME>               # フォーム/レポート、セクション、コントロールのプロパティ
jetdb form dump <FILE> <NAME> > form.bin     # 生の Blob ストリーム — 必ずリダイレクト
jetdb form dump -s typeinfo <FILE> <NAME> > typeinfo.bin   # blob（既定）| typeinfo | propdata | blobdelta
```

- `--forms-only` と `--reports-only` は同時に指定できない。同名のフォームとレポートは両方とも列挙される。
- フォームとレポートが名前を共有するとき、`controls`、`props`、`dump` には `-t form|report` を付ける。
- `form controls` は各セクションの後にそのコントロールを、`form props` と同じ順に並べる。3 列目はその一覧での位置（0 始まり）。未知のコントロール型は 16 進のコードで出る。
- `form props`: プロパティは `Application.SaveAsText` の名前で出す（`RecordSource`、`ControlSource`、`Filter`、`Caption`、`OnClick` など）。未知の ID は `0xXXXX`。Access 2000 形式では、その形式の ID を持たない後年のプロパティを ID に `0x8000` を足した値で出す（`0x8037` など）。テキストは `prop` と同じく引用・エスケープし、数値（色も含む）は SaveAsText と同じ符号付き、バイナリは `(N bytes)`、GUID は `{...}`、真偽値は `yes`/`no`、既定でない値に設定され値を持たない Yes/No プロパティは `NotDefault`。
- 名前がない → exit 1、`jetdb: form/report not found: <NAME>`。

```
$ jetdb form controls jetdb-sample.accdb frmOrders
詳細	Detail	0
txtOrderID	TextBox	1
lblOrderID	Label	2
...
btnShowTotal	CommandButton	13
```

```
$ jetdb form props jetdb-sample.accdb frmOrders
Form: frmOrders

  Form Properties:
    DividingLines               NotDefault
    ...
    RecordSource                "tblOrders"
    Caption                     "Orders"
    ...

  Control: txtOrderID (TextBox)
    ...
    Name           "txtOrderID"
    ControlSource  "OrderID"
    ...
```

### macro — マクロ

```
jetdb macro list <FILE>                       # 名前付きマクロ、1 行 1 名、ソート済み（-d / -1 は queries list と同じ）
jetdb macro show <FILE> <MACRO_NAME>          # SaveAsText のテキスト（改行は CRLF）
jetdb macro show --xml <FILE> <MACRO_NAME>    # マクロの XML
jetdb macro embedded <FILE> <NAME>            # フォーム/レポートの埋め込みマクロ: <event>EmMacro = Begin ... End のブロック
jetdb macro embedded --xml <FILE> <NAME>      # 1 行に 1 つの XML 文書（For = コントロール、Event = イベント）
jetdb macro data <FILE> <TABLE>               # テーブルのデータマクロを 1 つの DataMacros XML 文書で
jetdb macro data --xml <FILE> <TABLE>         # 各データマクロの格納されたままの XML、1 行に 1 つ
```

- `macro show` は XML なしで保存されたマクロ（Access 97 のマクロを含む）も読む。そのとき `--xml` は何も出さない。
- フォームとレポートが名前を共有するとき、`macro embedded` には `-t form|report` を付ける。
- 埋め込みマクロ・データマクロがない → exit 0 / 空 stdout。
- 名前がない → exit 1: `jetdb: macro not found: <NAME>`、`jetdb: form/report not found: <NAME>`、または `jetdb: table not found: <NAME>`（`macro data`）。

```
$ jetdb macro show macroGeneratedTestV2010.accdb act_Beep
Version =196611
PublishOption =1
ColumnsShown =0
Begin
    Comment ="_AXL:<?xml version='1.0' encoding='UTF-16' standalone='no'?><UserInterfaceMacro "
        "xmlns='http://schemas.microsoft.com/office/accessservices/2009/11/application'><"
        "Statements><Action Name='Beep'/></Statements>"
End
Begin
    Comment ="_AXL:</UserInterfaceMacro>"
End
```

```
$ jetdb macro embedded --xml macroGeneratedTestV2010.accdb frmEmbedded
<?xml version='1.0' encoding='UTF-16' standalone='no'?><UserInterfaceMacro Event='OnLoad' xmlns='http://schemas.microsoft.com/office/accessservices/2009/11/application'><Statements><Action Name='SetTempVar'><Argument Name='Name'>x</Argument><Argument Name='Expression'>2</Argument></Action></Statements></UserInterfaceMacro>
<?xml version='1.0' encoding='UTF-16' standalone='no'?><UserInterfaceMacro For='btnHello' Event='OnClick' xmlns='http://schemas.microsoft.com/office/accessservices/2009/11/application'><Statements><Action Name='MessageBox'><Argument Name='Message'>button clicked</Argument></Action></Statements></UserInterfaceMacro>
```

## 暗号化データベース

`.mdb`（Jet3 / Jet4）はパスワードなしで開ける。パスワード保護された `.accdb` には `--password` が要る:

```
jetdb --password "secret" tables protected.accdb
jetdb tables protected.accdb --password "secret"    # 同じ。--password はグローバル
```

## ワークフローパターン

### 未知のデータベースを調査する

```
jetdb ver -l data.mdb
jetdb tables data.mdb
jetdb schema data.mdb > schema.txt
jetdb queries list data.mdb
jetdb vba list data.mdb
jetdb form list data.mdb
jetdb macro list data.mdb
```

### 全テーブルをそれぞれのファイルにエクスポートする

```
jetdb tables data.accdb | while IFS= read -r t; do
  jetdb export data.accdb "$t" > "${t}.csv"
done
```

その後、stderr の `jetdb: warning:` と `wc -l` の行数を確認する。添付ファイル列のあるテーブルには `--attachments "att_${t}"` を足す。

### 移行先 RDBMS の DDL を生成する

```
jetdb schema data.accdb --ddl postgres > schema.sql
```

### 全 VBA モジュールを取り出す

```
jetdb vba list data.mdb | while IFS= read -r m; do
  jetdb vba show data.mdb "$m" > "${m}.bas"
done
```

### 全保存済みクエリをまとめる

```
jetdb queries list data.mdb | while IFS= read -r q; do
  printf '=== %s ===\n' "$q"
  jetdb queries show data.mdb "$q"
done > queries.sql
```

### 全名前付きマクロを取り出す

```
jetdb macro list data.accdb | while IFS= read -r m; do
  jetdb macro show data.accdb "$m" > "${m}.txt"
done
```

### フォームやレポートを調べる

```
jetdb form list data.accdb
jetdb form controls data.accdb "Orders"
jetdb form props data.accdb "Orders" > orders_props.txt
jetdb macro embedded data.accdb "Orders"
```

フォームとレポートが名前を共有するなら `-t form` か `-t report` を付ける。

## エラー時の挙動

- ファイルがない → exit 1、`jetdb: I/O error: <path>: No such file or directory (os error 2)`
- Access データベースでない → exit 1、`jetdb: format error: ...`
- パスワードが必要だが未指定 → exit 1、`jetdb: this database is password-protected`
- パスワードが違う → exit 1、`jetdb: invalid password`
- `schema -T`、`export`、`queries show`、`vba show`、`form dump|controls|props`、`macro show|embedded|data`、`prop` で名前がない → exit 1（`jetdb: table not found: ...`、`query not found`、`VBA module not found`、`form/report not found`、`macro not found`、`object not found`）
- 複数の種類のオブジェクトが共有する名前を `--type` なしで指定 → exit 1、`jetdb: objects of several types are named <NAME>: <types>; choose one with --type`
- Access 97 のフォームとレポート → exit 1、`jetdb: the forms and reports of Access 97 are not read`（`form list` は空出力）
- `export -d` が 1 文字でない → exit 1、`jetdb: delimiter must be one character, got '...'`
- list 系コマンドでデータなし、`prop` でプロパティなし、埋め込み / データマクロなし → exit 0 / 空 stdout
- エクスポートで行をスキップ → exit 0 で `jetdb: warning: <TABLE>: N row(s) skipped due to parse errors` — CSV は不完全として扱う
- 引数の誤り、同時に指定できないオプション、オプションだけでサブコマンドなし → exit 2、stderr は `error:` で始まる
- 引数なしの `jetdb` → exit 2、使い方を stderr に出す

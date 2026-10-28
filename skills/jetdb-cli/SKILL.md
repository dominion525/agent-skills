---
name: jetdb-cli
description: >
  Reads Microsoft Access (.mdb / .accdb) databases with the jetdb CLI 0.4: lists tables, shows schemas, exports CSV (including multi-value and attachment columns), generates DDL for SQLite / PostgreSQL / MySQL / Access, extracts VBA source, shows saved query SQL, inspects object properties and form / report designs (sections, controls, RecordSource, ControlSource, event handlers), and shows named macros, macros embedded in forms and reports, and table data macros as SaveAsText text or XML. Use when migrating Access to another RDBMS, extracting data from legacy MDB or ACCDB files, inspecting Jet3 (Access 97) through ACE17 (Access 2019) databases, or recovering VBA, queries, macros and form / report definitions, including from password-protected .accdb files.
allowed-tools: Bash, Read
---

# jetdb CLI

Read-only CLI for Microsoft Access (`.mdb` / `.accdb`) databases, version 0.4. Single Rust binary, no runtime dependencies.

```
cargo install jetdb-cli
```

## Operating Rules

```
jetdb [--password <PASS>] <COMMAND> [OPTIONS] <FILE> [ARGS]
```

- `--password` is a **global** option — it may appear before or after the subcommand.
- Object names (table, query, VBA module, form, report, macro, `prop` target) are matched **exactly, case included**. Always quote them — Access names often contain spaces and multibyte characters. Take names from the matching `list` command (or `tables`); never guess one.
- Objects of different types can share a name (a table, a form and a macro all named `Customers`; a form and a report both named `Shared`). `prop`, `form dump|controls|props` and `macro embedded` then fail and list the types; repeat with `-t/--type`.
- Stdout carries the result. Errors go to stderr as `jetdb: <message>`, warnings as `jetdb: warning: <message>`.
- Exit codes: success → 0; runtime error → 1; invalid arguments → 2 (stderr starts with `error:`). `jetdb` with no subcommand prints its usage to stderr and exits 2.
- List commands print one name per line, sorted. No data (no queries, no VBA, no macros) → exit 0 with empty stdout, not an error.
- `export`, `vba show`, `macro` and `form props` can be large. **Redirect large output to a file** (`> out.csv`) and inspect the file. Piping into `head -n N` for a peek is safe (jetdb ends quietly when the pipe closes).
- `form dump` writes raw binary. Always redirect it to a file; never let the bytes reach the conversation.
- Check stderr for `jetdb: warning:` lines even when the exit code is 0. In particular `export` warns `jetdb: warning: <TABLE>: N row(s) skipped due to parse errors` — the CSV is then incomplete.
- Text: Jet3 (Access 97) text is read in the code page of the database (such as 1252, or 932 for Japanese), Jet4 and ACE text as UTF-16LE; all output is UTF-8.

## Commands

### ver — Engine version

```
jetdb ver <FILE>              # JET3 | JET4 | ACE12 | ACE14 | ACE15 | ACE16 | ACE17
jetdb ver -l <FILE>           # Long form
```

```
$ jetdb ver nwind.mdb
JET3
$ jetdb ver -l nwind.mdb
Jet3 (Access 97)
```

### tables — List tables

```
jetdb tables <FILE>           # User tables, one per line, sorted
jetdb tables -s <FILE>        # Also tables with the SYSTEM or HIDDEN flag (MSys*, f_..._Data, ...)
jetdb tables -T <FILE>        # Prefix the type name (table / systable), tab-separated
jetdb tables -t <FILE>        # Prefix the type number (1 for every table), tab-separated
```

`-t` and `-T` are mutually exclusive. Only `-T` tells user tables from system tables.

```
$ jetdb tables jetdb-sample.accdb
tblCustomers
tblOrders
tblProducts
```

### schema — Table structure and DDL

```
jetdb schema <FILE>                      # All user tables, human-readable
jetdb schema <FILE> -T <TABLE>           # One table
jetdb schema <FILE> --ddl postgres       # sqlite | postgres | mysql | access
jetdb schema <FILE> --no-indexes --no-relations
```

- The human form prints `Columns:`, `Indexes:` and `Relationships:` per table. Columns are in Design View order; Text sizes are in characters. `NOT NULL` marks a required column, `AUTO` an AutoNumber, `CALC` a calculated column (shown with the type of its result).
- The DDL form emits `CREATE TABLE`, `CREATE INDEX` and `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY`. A relationship without referential integrity is written as a `--` comment, not a foreign key (left out in Access DDL). GUID AutoNumber columns get a GUID default where the dialect has one.
- `--no-indexes` / `--no-relations` apply to both forms.
- Unknown `-T` table → exit 1, `jetdb: table not found: <NAME>`.

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

### export — CSV export

```
jetdb export <FILE> <TABLE>                         # RFC 4180 CSV to stdout
jetdb export <FILE> <TABLE> -H                      # No header row
jetdb export <FILE> <TABLE> -d $'\t'                # Delimiter: exactly one character (default ,)
jetdb export <FILE> <TABLE> -D "%d/%m/%Y"           # Format of dates without a time (default %Y-%m-%d)
jetdb export <FILE> <TABLE> -T "%Y-%m-%dT%H:%M:%S"  # Format of dates with a time (default "%Y-%m-%d %H:%M:%S")
jetdb export <FILE> <TABLE> -b strip                # Binary: strip | raw | octal | hex (default hex)
jetdb export <FILE> <TABLE> -0 NULL                 # NULL text (default: empty)
jetdb export <FILE> <TABLE> -B                      # Booleans as TRUE/FALSE (default 1/0)
jetdb export <FILE> <TABLE> -s                      # Include hidden columns (HIDDEN flag)
jetdb export <FILE> <TABLE> --attachments <DIR>     # Write attachment files under DIR
```

- `-d` takes exactly one character. An empty or longer value fails with exit 1: `jetdb: delimiter must be one character, got '\t'`. In bash/zsh write a tab as `-d $'\t'`; `"\t"` is a backslash and `t`.
- By default the columns Access maintains and hides are left out; `-s` includes them. System tables are always exported with all their columns.
- Text, GUID and extended date/time values are always quoted. Other values are quoted only when they contain the delimiter, a quote or a line break.
- A Date/Time value with no time of day uses `-D`; others use `-T` (strftime subset).
- Binary modes: `strip` empty field; `raw` bytes as lossy UTF-8; `octal` `\NNN` per byte; `hex` lowercase hex.
- Complex columns (Access 2007+): multiple values → the values joined by `;` in one quoted field; attachments → the file names joined by `;`; append-only Long Text history → a number (an ID, not a count; the Long Text column itself holds the latest text). No values → empty field.
- `--attachments <DIR>` writes each file to `<DIR>/<number>/<file name>` (`/` and `\` in names become `_`) and puts those paths, relative to `<DIR>`, in the field.
- Rows are streamed, so large tables do not need to fit in memory. Redirect to a file, then check `wc -l` and stderr.

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

### queries — Saved queries

```
jetdb queries list <FILE>                  # One name per line, sorted
jetdb queries list -d "|" <FILE>           # All names on one line, joined by the string
jetdb queries show <FILE> <QUERY_NAME>     # Reconstructed SQL
```

- On `queries list`, `vba list`, `form list` and `macro list`: `-d` takes any string; `-1` is accepted for compatibility and does nothing; `-1` and `-d` together are an argument error (exit 2).
- If rows of MSysQueries cannot be read, `queries show` fails rather than print SQL that may miss parts (`jetdb: query <NAME> may be incomplete: rows of MSysQueries could not be read`).

```
$ jetdb queries show jetdb-sample.accdb qryMonthlySales
SELECT Format(tblOrders.OrderDate, 'yyyy-mm') AS SalesMonth, tblCustomers.CustomerName, Sum(tblOrders.Quantity * tblProducts.UnitPrice) AS Total
FROM (tblOrders INNER JOIN tblCustomers ON tblOrders.CustomerID = tblCustomers.CustomerID) INNER JOIN tblProducts ON tblOrders.ProductID = tblProducts.ProductID
GROUP BY Format(tblOrders.OrderDate, 'yyyy-mm'), tblCustomers.CustomerName
ORDER BY Format(tblOrders.OrderDate, 'yyyy-mm'), tblCustomers.CustomerName;
```

### vba — VBA modules

```
jetdb vba list <FILE>                      # One name per line, sorted
jetdb vba list -d "|" <FILE>               # One line, joined by the string
jetdb vba show <FILE> <MODULE_NAME>        # Full source (UTF-8)
```

```
$ jetdb vba list -d "|" jetdb-sample.accdb
Form_frmOrders|modBilling
```

### prop — Object properties (LvProp)

```
jetdb prop <FILE> <OBJECT_NAME>
jetdb prop -t <TYPE> <FILE> <OBJECT_NAME>
```

- `-t/--type`: `table`, `query`, `form`, `report`, `macro`, `module`, `linkedtable`, `linkedodbctable`, `relationship`, `container`, `database`, `dbproperty`, `userinfo`.
- Output: `Object: <NAME>`, then the object's own properties headed with its type in words (`Table Properties:`, `Query Properties:`, `Macro Properties:`, `Linked Table Properties:`, ...; `Object Properties:` when the type is unknown), then `Column: <NAME>` blocks and `Additional Properties:` blocks in stored order.
- Text values are in double quotes with `\\`, `\"`, `\r`, `\n`, `\t` and `\u{..}` escapes, so each property is one line. Binary values show as `(N bytes)`, GUIDs as `{...}`, booleans as `yes`/`no`.
- A missing object → exit 1, `jetdb: object not found: <NAME>` (`table not found: ...` etc. with `--type`). An object that exists but has no properties → exit 0, empty stdout.

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

### form — Forms and reports

Read for Access 2000 and later (Jet4 and ACE). The forms and reports of Access 97 (Jet3) are not read: `form list` prints nothing, and `form dump|controls|props` (and `macro embedded`) fail with `jetdb: the forms and reports of Access 97 are not read` (exit 1).

```
jetdb form list <FILE>                       # Forms and reports, one per line, sorted
jetdb form list --forms-only <FILE>          # Forms only (--reports-only: reports only)
jetdb form list -d "|" <FILE>                # One line, joined by the string
jetdb form controls <FILE> <NAME>            # Sections and controls: name<TAB>type<TAB>position
jetdb form props <FILE> <NAME>               # Properties of the form/report, its sections and controls
jetdb form dump <FILE> <NAME> > form.bin     # Raw Blob stream — ALWAYS redirect
jetdb form dump -s typeinfo <FILE> <NAME> > typeinfo.bin   # blob (default) | typeinfo | propdata | blobdelta
```

- `--forms-only` and `--reports-only` are mutually exclusive. A form and a report with the same name are both listed.
- `controls`, `props` and `dump` take `-t form|report` when a form and a report share the name.
- `form controls` lists each section followed by its controls, in the order `form props` shows them; the third column is the position in that list, from 0. Unknown control types show as their hex code.
- `form props`: properties are named as `Application.SaveAsText` names them (`RecordSource`, `ControlSource`, `Filter`, `Caption`, `OnClick`, ...); unknown IDs show as `0xXXXX`, and for the Access 2000 format a later property without an ID of that format as the ID plus `0x8000` (such as `0x8037`). Text is quoted and escaped as in `prop`; numbers, colors included, are signed as SaveAsText writes them; binary shows as `(N bytes)`, GUIDs as `{...}`, booleans as `yes`/`no`, and a Yes/No property set to its non-default value without a value as `NotDefault`.
- Unknown name → exit 1, `jetdb: form/report not found: <NAME>`.

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

### macro — Macros

```
jetdb macro list <FILE>                       # Named macros, one per line, sorted (-d / -1 as in queries list)
jetdb macro show <FILE> <MACRO_NAME>          # SaveAsText text (CRLF line endings)
jetdb macro show --xml <FILE> <MACRO_NAME>    # The macro's XML
jetdb macro embedded <FILE> <NAME>            # Embedded macros of a form/report: <event>EmMacro = Begin ... End blocks
jetdb macro embedded --xml <FILE> <NAME>      # One XML document per line (For = control, Event = event)
jetdb macro data <FILE> <TABLE>               # Data macros of a table as one DataMacros XML document
jetdb macro data --xml <FILE> <TABLE>         # Each data macro's XML as stored, one per line
```

- `macro show` also reads macros saved without XML, including Access 97 macros; `--xml` then prints nothing.
- `macro embedded` takes `-t form|report` when a form and a report share the name.
- No embedded macros / no data macros → exit 0, empty stdout.
- Unknown names → exit 1: `jetdb: macro not found: <NAME>`, `jetdb: form/report not found: <NAME>`, or `jetdb: table not found: <NAME>` (`macro data`).

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

## Encrypted Databases

`.mdb` files (Jet3 / Jet4) open without a password. A password-protected `.accdb` needs `--password`:

```
jetdb --password "secret" tables protected.accdb
jetdb tables protected.accdb --password "secret"    # same; --password is global
```

## Workflow Patterns

### Survey an unknown database

```
jetdb ver -l data.mdb
jetdb tables data.mdb
jetdb schema data.mdb > schema.txt
jetdb queries list data.mdb
jetdb vba list data.mdb
jetdb form list data.mdb
jetdb macro list data.mdb
```

### Export every table to its own file

```
jetdb tables data.accdb | while IFS= read -r t; do
  jetdb export data.accdb "$t" > "${t}.csv"
done
```

Then check stderr for `jetdb: warning:` and the row counts with `wc -l`. Add `--attachments "att_${t}"` for tables with attachment columns.

### Generate target-RDBMS DDL

```
jetdb schema data.accdb --ddl postgres > schema.sql
```

### Extract every VBA module

```
jetdb vba list data.mdb | while IFS= read -r m; do
  jetdb vba show data.mdb "$m" > "${m}.bas"
done
```

### Snapshot every saved query

```
jetdb queries list data.mdb | while IFS= read -r q; do
  printf '=== %s ===\n' "$q"
  jetdb queries show data.mdb "$q"
done > queries.sql
```

### Extract every named macro

```
jetdb macro list data.accdb | while IFS= read -r m; do
  jetdb macro show data.accdb "$m" > "${m}.txt"
done
```

### Inspect a form or report

```
jetdb form list data.accdb
jetdb form controls data.accdb "Orders"
jetdb form props data.accdb "Orders" > orders_props.txt
jetdb macro embedded data.accdb "Orders"
```

If the name is shared by a form and a report, add `-t form` or `-t report`.

## Error Behaviour

- File not found → exit 1, `jetdb: I/O error: <path>: No such file or directory (os error 2)`
- Not an Access database → exit 1, `jetdb: format error: ...`
- Password required but missing → exit 1, `jetdb: this database is password-protected`
- Wrong password → exit 1, `jetdb: invalid password`
- Unknown name on `schema -T`, `export`, `queries show`, `vba show`, `form dump|controls|props`, `macro show|embedded|data`, `prop` → exit 1 (`jetdb: table not found: ...`, `query not found`, `VBA module not found`, `form/report not found`, `macro not found`, `object not found`)
- Name shared by objects of several types without `--type` → exit 1, `jetdb: objects of several types are named <NAME>: <types>; choose one with --type`
- Access 97 forms and reports → exit 1, `jetdb: the forms and reports of Access 97 are not read` (`form list` gives empty output)
- `export -d` not one character → exit 1, `jetdb: delimiter must be one character, got '...'`
- No data on a list command, no properties on `prop`, no embedded / data macros → exit 0, empty stdout
- Skipped rows on export → exit 0 with `jetdb: warning: <TABLE>: N row(s) skipped due to parse errors` — treat the CSV as incomplete
- Invalid arguments, conflicting options, or options without a subcommand → exit 2, stderr starts with `error:`
- `jetdb` with no arguments → exit 2, the usage on stderr

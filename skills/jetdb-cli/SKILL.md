---
name: jetdb-cli
description: >
  Reads Microsoft Access (.mdb / .accdb) databases: lists tables, shows schemas,
  exports CSV, generates DDL for SQLite / PostgreSQL / MySQL / Access,
  extracts VBA source, dumps saved query SQL, and inspects form / report design
  properties such as RecordSource, ControlSource, and event handlers.
  Use when migrating Access to another RDBMS, extracting data from legacy MDB
  or ACCDB files, inspecting Jet3 (Access 97) through ACE17 (Access 2019) schemas,
  or recovering VBA modules and form / report definitions from password-protected databases.
allowed-tools: Bash, Read
---

# jetdb CLI

Read-only CLI for Microsoft Access (`.mdb` / `.accdb`) databases. Single Rust binary, no runtime dependencies.

```
cargo install jetdb-cli
```

## Operating Rules

```
jetdb [--password <PASS>] <COMMAND> [OPTIONS] <FILE> [ARGS]
```

- `--password` is a **global** flag — it may appear before or after the subcommand.
- Object names (table, query, VBA module, form, report, `prop` target) are matched by **exact-case string comparison**. Always quote them — Access names commonly contain spaces, multibyte characters, and case-sensitive variants. Use the relevant `list` command as the source of truth; never guess a name.
- Stdout carries successful payload; warnings and runtime errors go to stderr as `jetdb: ...` (warnings as `jetdb: warning: ...`).
- Exit codes: success → 0, runtime error → 1, invalid CLI arguments → 2 (Clap default, stderr starts with `error:`).
- `list`-style commands with no data → exit 0 with empty stdout (not an error).
- `export` and `vba show` stream their full result to stdout. **Always redirect large output to a file** (`> out.csv`) and inspect the file — do not let the agent read the raw stream.
- After every `export`, scan stderr for `jetdb: warning: N row(s) skipped`. Exit code is still 0 but the CSV is incomplete in that case.
- Text decoding: Jet3 (Access 97) uses Latin-1, Jet4+ and ACE use UTF-16LE; both are emitted as UTF-8. Jet3 databases authored on non-Latin-1 systems (e.g. Japanese CP932) may surface as mojibake — that limitation is in the source file, not in the conversion.

## Commands

### ver — Engine version

```
jetdb ver <FILE>              # Short token: JET3 | JET4 | ACE12 .. ACE17
jetdb ver -l <FILE>           # Long form, e.g. "Jet4 (Access 2000/2003)"
```

### tables — List tables

```
jetdb tables <FILE>           # User tables, one per line, sorted
jetdb tables -s <FILE>        # Include system tables (MSys*)
jetdb tables -T <FILE>        # Prefix type name (table / systable), tab-separated
jetdb tables -t <FILE>        # Prefix numeric type code, tab-separated
```

`-t` and `-T` are mutually exclusive.

Output example:

```
$ jetdb tables -s -T data.mdb
systable	MSysACEs
systable	MSysObjects
table	Customers
table	Orders
```

### schema — Table structure and DDL

```
jetdb schema <FILE>                      # All user tables, human-readable
jetdb schema <FILE> -T <TABLE>           # Single table
jetdb schema <FILE> --ddl sqlite         # sqlite | postgres | mysql | access
jetdb schema <FILE> --no-indexes --no-relations
```

`--no-indexes` and `--no-relations` apply to both human and DDL output. Human form prints `Columns:`, `Indexes:`, `Relationships:` sections. DDL form emits `CREATE TABLE`, `CREATE INDEX`, and `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` statements.

Output example (human-readable):

```
Table: Customers

  Columns:
    ID    Long         NOT NULL AUTO
    Name  Text(100)
    Email Text(200)

  Indexes:
    PrimaryKey  [ID ASC]  UNIQUE REQUIRED
```

### export — CSV export

```
jetdb export <FILE> <TABLE>                              # RFC 4180 CSV to stdout
jetdb export <FILE> <TABLE> -H                           # Suppress header row
jetdb export <FILE> <TABLE> -d $'\t'                     # Tab-delimited (literal "\t" does NOT work)
jetdb export <FILE> <TABLE> -D "%Y-%m-%d"                # Date format (strftime)
jetdb export <FILE> <TABLE> -T "%Y-%m-%dT%H:%M:%S"       # DateTime format
jetdb export <FILE> <TABLE> -b hex                       # Binary mode (default: hex)
jetdb export <FILE> <TABLE> -0 NULL                      # NULL placeholder (default: empty string)
jetdb export <FILE> <TABLE> -B                           # Booleans as TRUE/FALSE (default: 1/0)
jetdb export <FILE> <TABLE> -s                           # Include replication columns
```

- `-d/--delimiter` accepts a string but uses only the first character (warns otherwise). For tab in bash/zsh use `-d $'\t'`; `"\t"` is a literal backslash-t.
- `-b` modes (default `hex`):
  - `strip` — drop binary entirely (empty cell)
  - `raw` — UTF-8 lossy decode, CSV-escaped only if it contains delimiter / quote / newline
  - `octal` — `\NNN` per byte
  - `hex` — lowercase hex per byte
- Text and GUID values are always quoted; numeric values are unquoted.
- The full table is read into memory and streamed to stdout. For large tables redirect to a file, then `wc -l` / `head` to verify.

Output example:

```
ID,Name,Email,Active
1,"Alice","alice@example.com",1
2,"Bob","bob@example.com",0
```

### queries — Saved queries

```
jetdb queries list <FILE>                  # Space-separated, sorted
jetdb queries list -1 <FILE>               # One per line
jetdb queries list -d , <FILE>             # Custom delimiter (first char only)
jetdb queries show <FILE> <QUERY_NAME>     # Print reconstructed SQL
```

`-1` and `-d` are mutually exclusive.

### vba — VBA modules

```
jetdb vba list <FILE>                      # Space-separated, sorted
jetdb vba list -1 <FILE>                   # One per line
jetdb vba list -d , <FILE>                 # Custom delimiter
jetdb vba show <FILE> <MODULE_NAME>        # Print full source (UTF-8)
```

`-1` and `-d` are mutually exclusive.

### form — Forms and reports

Jet4 / ACE only. Access 97 (Jet3) does not store form/report design in the `MSysAccessStorage` format that `form` parses.

```
jetdb form list <FILE>                     # Forms + reports, space-separated, sorted
jetdb form list -1 <FILE>                  # One per line
jetdb form list -d , <FILE>                # Custom delimiter
jetdb form list --forms-only <FILE>        # Forms only
jetdb form list --reports-only <FILE>      # Reports only
jetdb form dump <FILE> <NAME>              # Dump default Blob stream to stdout — REDIRECT to file
jetdb form dump <FILE> <NAME> -s typeinfo  # Streams: blob (default) | typeinfo | propdata | blobdelta
jetdb form controls <FILE> <NAME>          # name<TAB>type<TAB>index, one per line
jetdb form props <FILE> <NAME>             # Pretty-printed form / control properties
```

- `--forms-only` and `--reports-only` are mutually exclusive; `-1` and `-d` are mutually exclusive.
- `form dump` writes **raw binary** to stdout. Always redirect (`> form.blob`) — never let the bytes hit the conversation.
- `form controls`: known control codes resolve to type names (e.g. `TextBox`, `CommandButton`, `Label`); unknown codes appear as `0xNNNN`.
- `form props`: properties come from the Blob payload (`RecordSource`, `ControlSource`, `Filter`, `Caption`, `FontName`, `Format`, event handlers like `OnClick`, etc.). Binary values render as `(N bytes)`, GUIDs as `{…}`, booleans as `yes`/`no`. Control type names are taken from TypeInfo when available; otherwise the type displays as `0x0000`.

Output example (`form controls`):

```
$ jetdb form controls data.accdb F_Customers
Txt_Name	TextBox	1
Btn_Save	CommandButton	2
Lbl_Title	Label	3
```

Output example (`form props`):

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

### prop — Object LvProp

```
jetdb prop <FILE> <OBJECT_NAME>
```

Shows LvProp values grouped into Table Properties, per-column blocks, and Additional Properties.

Note: if the object name does not exist, or has no LvProp data, `prop` exits 0 with empty stdout — there is no "not found" error. Confirm the name against `jetdb tables` (or the relevant `list` command) first.

## Encrypted Databases

`.mdb` (Jet3 / Jet4) uses Jet RC4 obfuscation that jetdb undoes transparently — no password needed.
`.accdb` (ACE12+) may be password-protected:

```
jetdb --password "secret" tables protected.accdb
# or equivalently (--password is global)
jetdb tables protected.accdb --password "secret"
```

## Workflow Patterns

### Survey an unknown database

```
jetdb ver data.mdb
jetdb tables -s data.mdb
jetdb schema data.mdb
```

### Export a table for analysis (always to file)

```
jetdb tables data.mdb
jetdb schema data.mdb -T Customers
jetdb export data.mdb Customers > customers.csv
head -n 5 customers.csv
wc -l customers.csv
```

### Generate target-RDBMS DDL

```
jetdb schema data.mdb --ddl postgres > schema.sql
```

### Extract every VBA module to its own file

```
jetdb vba list -1 data.mdb | while IFS= read -r mod; do
  jetdb vba show data.mdb "$mod" > "${mod}.bas"
done
```

### Snapshot every saved query as one SQL file

```
jetdb queries list -1 data.mdb | while IFS= read -r q; do
  printf '=== %s ===\n' "$q"
  jetdb queries show data.mdb "$q"
done > queries.sql
```

### Inspect form / report design

```
jetdb form list data.accdb
jetdb form props data.accdb F_Main
jetdb form controls data.accdb F_Main
```

## Error Behaviour

- File not found / unreadable → exit 1
- Wrong file format → exit 1
- Password required but missing → exit 1, stderr: `jetdb: this database is password-protected`
- Password incorrect → exit 1, stderr: `jetdb: invalid password`
- `*show` / `form dump|controls|props` with an unknown object name → exit 1
- `prop` with an unknown object name or no LvProp → exit 0, empty stdout (silent)
- `list`-style command with no data → exit 0, empty stdout
- Partial export → exit 0 with `jetdb: warning: N row(s) skipped` on stderr — treat the CSV as incomplete
- Invalid CLI arguments → exit 2, stderr starts with `error:`

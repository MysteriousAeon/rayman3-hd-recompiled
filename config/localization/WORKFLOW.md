# Translating Rayman 3 HD Recompiled into Turkish: the workflow

English game text → first draft by an AI → second opinion by another model (e.g. Gemini) → your decisions → a checked
mod with **only your approved strings** → Settings → Mods.

Tools: `tools/r3hd_locflow.py` (the workflow) on top of `tools/r3hd_loc.py` (check / build engine) and
`tools/r3hd_mods.py` (mods). Standard Python, no API key, no network: you hand files to any AI yourself.

## What stays private

- **Exports** (`export`, `r3hd_loc.py catalog`) contain the game's English text. Keep them in `private/` or outside the
  repository; the tool refuses to write them into the repository elsewhere. Sending a batch to an online AI service
  sends that text to the service: your decision, never automatic.
- **Your project** (`tr.json`) holds hashes of the English strings, your Turkish text and review notes, never the
  English. Keep it in a private folder too (e.g. `private/tr/`), with a backup of your own.

## The project file

One JSON file. Each string is keyed by a stable id that never changes between exports and review rounds:

| id | what it is |
|---|---|
| `en.471` | handle 471 of the English text table (menus, dialogs, tutorial boxes, spoken lines) |
| `vs.en.42.3` | movie subtitle: movie 42 (`menu10.bik`), its 4th English cue |

```json
"en.12": {"source_sha256": "<64 hex>", "status": "reviewed", "text": "Yarışa başla", "origin": "draft:batch_001",
          "review": {"by": "gemini", "verdict": "change", "suggestion": "Yarışı başlat", "note": "imperative"}}
```

Statuses: `draft` (first draft) → `reviewed` (a reviewer looked at it) → `approved` (you accepted it). `needs_review`
= sent back (by you, or because the game's English changed). **Only your own decision changes an approved text**; drafts
and reviews never overwrite it (a review of an approved string waits as a suggestion).

## Step by step

All commands from the repository folder; `P` = your project, e.g. `private/tr/tr.json`.

**1. Create the project and export the English** (once):

```bash
python tools/r3hd_locflow.py init private/tr/tr.json --id tr.full --name "Türkçe"
python tools/r3hd_locflow.py export private/tr/tr.json private/tr/out --for draft --batch-size 150
```

`private/tr/out/batch_001.jsonl` … : the untranslated strings with id, a `check` (the first characters of the source
hash), kind, category (`voiced line`, `movie subtitle`, or empty when nothing in the data says what it is), the levels
and speaker codes of voiced lines (from the sound banks: codes such as a four-letter abbreviation, never a guessed
name), size and line count, in-band codes, the English, and an empty `turkish`. Use `--ids vs.en.` for subtitles only,
`--ext .csv` for spreadsheet batches, `--only draft,needs_review` to re-export.

**2. First AI draft.** Give each batch to the model with `config/localization/prompts/draft.md`; save its answer as
e.g. `private/tr/in/batch_001.jsonl` (CSV / TSV / JSON lists work too), then:

```bash
python tools/r3hd_locflow.py import private/tr/tr.json private/tr/in/batch_001.jsonl --from draft --label claude-b001
```

Each row is checked. **Rejected**: an unknown or duplicated id, a `check` that does not belong to the id (shifted
rows), an edited English, a dropped or altered code (`\jc`, `\f1:…`), a character the game cannot draw, a real line
break. **Skipped**: approved and reviewed strings (`--overwrite-unapproved` replaces reviewed ones, never approved).
**Warnings**: line-break count, spaces, end punctuation, capitals, all-caps `I` (İ?), text identical to the English,
longer than the slot. Add `--dry-run` to see the report without writing. The previous project is kept as `tr.json.bak`.

**3. Second opinion (Gemini or another model).**

```bash
python tools/r3hd_locflow.py export private/tr/tr.json private/tr/review_001.jsonl --for review
```

Give it to the reviewer with `config/localization/prompts/review.md`. It fills `verdict` (`ok` / `change` /
`question`), `suggestion` (the whole new text, for `change`) and `review_note`.

**4. Import the review.**

```bash
python tools/r3hd_locflow.py import private/tr/tr.json private/tr/review_001_done.jsonl --from review --label gemini
```

Nothing is overwritten: suggestions are stored beside the text. A row whose `turkish` differs from the project's
current text is rejected (the reviewer saw an older version, or edited the text instead of suggesting).

**5. Your decisions.** Export a sheet and open it in a spreadsheet (UTF-8 CSV):

```bash
python tools/r3hd_locflow.py export private/tr/tr.json private/tr/decide.csv --for human
```

Columns include the English, the current Turkish, the reviewer's verdict / suggestion / note and `problems` (machine
checks). Fill `decision` per row:

| decision | effect |
|---|---|
| `approve` | the row's `turkish` column (edit it first if you like) becomes the approved text |
| `accept` | the reviewer's suggestion becomes the approved text |
| `reject` | the suggestion is dropped, the text stays |
| `redo` | back to `needs_review` (re-draft or re-review it later) |
| empty | nothing changes |

Save as CSV UTF-8, then `import private/tr/tr.json private/tr/decide.csv --from human`. Keep the `text_check`
column: a row whose string changed in the project after the sheet was exported is rejected, so an old sheet never
replaces a newer text. (A new draft for a string that is still `draft` simply replaces the old draft and its review.)

**6. Validate.**

```bash
python tools/r3hd_locflow.py status private/tr/tr.json --report private/tr/status.md
python tools/r3hd_locflow.py validate private/tr/tr.json --glossary private/tr/glossary.json
```

`status`: counts per status, missing strings by kind, stale strings (the game's English changed), pending suggestions,
unknown ids. `validate`: every entry's machine checks, glossary hints (`config/localization/tr/glossary.example.json`
shows the format; you maintain the terms), then a check of the whole project as one mod against your game data (room
for moved text, the subtitle budget, glyphs, line widths). **Machine checks never judge meaning, tone, humour or a
character's voice**: that is the reviewer's and, finally, yours.

**7. Build and install.**

```bash
python tools/r3hd_locflow.py build private/tr/tr.json private/tr/build/tr-full --zip
```

Only `approved` strings go in (the report counts what was left out). Install the zip in **Settings → Mods → Install**
(or `python tools/r3hd_mods.py import private/tr/build/tr-full.zip`), enable it, play. For a private test of
unapproved text, `--allow-unapproved` builds a separate mod (id `….dev`, name marked "DEV: unreviewed text"): never share
it.

**8. Later updates.** Keep the same project. New drafts only fill missing / draft strings, so approvals survive any
number of rounds; export `--only missing,draft,needs_review` for the next batch. After a game-data change,
`refresh` marks strings whose English changed as `needs_review` (text kept), and `import` refuses rows for them until
then. Build again with a higher `version` in the project and install it over the old one (same id).

## A translation workspace (M37): the production layer

For the whole game, use `tools/r3hd_trwork.py`: it keeps the project, glossary, style guide, batches, review rounds,
decision sheets and builds in one folder that can later become a repository of its own (for example
`rayman3hd-turkish`), with every English-bearing file under its `private/` folder. Its `README.md` (copied from
`config/localization/project_template/`) lists the commands; in short:

```bash
python tools/r3hd_trwork.py new private/tr/rayman3hd-turkish
python tools/r3hd_trwork.py inventory private/tr/rayman3hd-turkish
python tools/r3hd_trwork.py batch private/tr/rayman3hd-turkish --category menu,tutorial --readiness ready --size 40
python tools/r3hd_trwork.py ingest private/tr/rayman3hd-turkish ANSWER.jsonl --batch r001/batch_001 --model NAME
python tools/r3hd_trwork.py review private/tr/rayman3hd-turkish --size 60
python tools/r3hd_trwork.py review-in private/tr/rayman3hd-turkish ANSWER.jsonl --reviewer gemini
python tools/r3hd_trwork.py sheet private/tr/rayman3hd-turkish
python tools/r3hd_trwork.py decide private/tr/rayman3hd-turkish private/tr/rayman3hd-turkish/private/sheets/sheet_001.csv
python tools/r3hd_trwork.py dashboard private/tr/rayman3hd-turkish --report private/tr/rayman3hd-turkish/private/dashboard.md
python tools/r3hd_trwork.py queue private/tr/rayman3hd-turkish
python tools/r3hd_trwork.py build private/tr/rayman3hd-turkish --preview --ids-file IDS.txt --zip
python tools/r3hd_trwork.py build private/tr/rayman3hd-turkish --release --zip
```

What it adds to the steps above:

- **Context.** Every string gets a category (menu, system, tutorial, bonus_help, album, credits, dialogue, subtitle,
  internal, legacy, placeholder; `config/localization/context_groups.json`), a readiness (`ready`, `partial_context`,
  `needs_context`, `verify_display`) and flags (codes, buttons, placeholders, line breaks, same English as another id,
  shared with the other languages' tables). Translate `ready` strings first; never invent a scene for the others.
- **Rounds with manifests.** A draft round writes batches and a manifest of their ids; `ingest` takes one model answer
  for one batch and also refuses rows of other batches; missing rows are listed and `retry` exports them again. The
  provenance is `draft:<model>.r001.batch_001`; `ledger.jsonl` records every import (file hash, counts, no text).
- **Review rounds** are numbered; an older round never replaces a newer pending review.
- **Decision sheets** add `final` (your own text for `approve`), `human_note`, the draft's origin and the context.
- **Dashboard and queue**: coverage by category and status, invalid entries, missing context, and draft coverage
  apart from approved coverage (100 % drafted is not a finished translation); the queue lists invalid, stale, pending
  decisions, questions, overflow, terminology, context and unreviewed rows in that order.
- **Builds**: `--preview` (every status; id `….dev`, name and description NOT FINAL; `--ids` for a sample) and
  `--release` (approved only), both checked against your game data and port version.

### Returned review rounds (M47)

When a reviewer returns many batches of several overlapping rounds, do not `review-in` them one by one (the last
round would silently win, and a returned file with drifted metadata, such as a wrong `round`, would be stored as it
is). `tools/m47_review_audit.py` does it in four steps, writing only under the workspace's `private/m47/`:

```bash
python tools/m47_review_audit.py audit WS --expect r001=7:375,r002=14:816   # each returned rNNN_batch_NNN.tsv
python tools/m47_review_audit.py merge WS --resolution RES.tsv               # one row per id
python tools/m47_review_audit.py apply WS --isolated                         # on a copy, twice
python tools/m47_review_audit.py apply WS                                    # then verify WS
```

- **audit** compares every returned table with the batch it was exported as (ids, order, English, Turkish and
  metadata; only `verdict`, `suggestion`, `review_note` are the reviewer's), restores drifted metadata from the export
  into a derived copy (the returned file is never changed), refuses what cannot be repaired (another Turkish was
  reviewed, rows missing, moved or invented), and runs the project's importer on an isolated copy.
- **merge** takes the latest non-ok review of each id (a later `ok` never hides an earlier `change`), checks the
  editorial decision files against the reviews, and needs a resolution row (`integrate`, `keep` or `hold`, with a
  group and a reason) for every id with a non-ok verdict or an editorial row.
- **apply** stores the consolidated review with `review-in`, adds proposals (`proposals.tsv` beside the merge, kind
  `proposal`) and runs `r3hd_trwork.py integrate`: a reviewer's **stored suggestion** becomes the working text for
  previews, the entry stays `reviewed` (never approved), the replaced text is kept as a `previous_draft`
  alternative, origin `integrated:<reviewer>.r<round>`. The ledger guards every step: a rerun changes nothing.

Spreadsheets: cells that begin with `=` `+` `-` `@` are written with a leading apostrophe and checks as `#hex`, so a
spreadsheet cannot run or reformat them; both are restored on import. A semicolon CSV (Excel in a Turkish locale)
imports too. The game's font has no `;` `<` `>` `{` `}` and no `…`: rows with them are refused.

## Human LQA while playing (review workbook)

For a person's corrections found in game, `tools/r3hd_lqa.py build OUT.xlsx` writes one private workbook (under
`private/` only; never overwritten): every translatable string with its String ID, region (from verified data, or
marked INFERRED / Unmapped), the English, the installed Turkish, and blank **Proposed Turkish**, **Review Note**,
**Status** and **Batch** columns. `check BOOK.xlsx` compares the reference columns with the snapshot inside the
workbook and with the live game text and mod (edited → error; changed source → STALE) and checks every proposal like
an import (codes, placeholders, `\l`, letters the font draws, subtitle size). `export BOOK.xlsx OUT.jsonl --region
TEXT | --batch NAME | --all` writes the reviewed rows with both hashes; it applies nothing. Corrections then enter
the workspace as the person's decisions (`r3hd_trwork.py`). Report: `reports/release_ux/LQA_WORKBOOK.md`.

## Limits to know

- **Subtitles** (`vs.*`): since port 0.36.0 the movie subtitle table may grow (by up to 1 MiB; the English cues are
  3,122 bytes with their length fields), so Turkish subtitles may be longer than the English. On an older port the
  total must stay within the original file (`build` refuses with the overage). Each subtitle: at most 400 bytes;
  the banner was seen with one or two lines (`\l`), so `validate` warns at three. `status` shows the balance
  (`subtitle_bytes_vs_english`). Timing and order are the game's and cannot be edited.
- **Validation report**: `validate … --report private/tr/findings.csv` (or `.md`) lists every finding with its id,
  severity, stage (`encoding` the game cannot store or draw it, `format` codes and breaks, `capacity` room in the
  game's files, `layout` how it will look, `compatibility`, `source`, `review` / `style` advice), the constraint and a
  suggested action. Nothing in it changes your text; the decisions stay yours.
- **Importing the same human sheet twice** is harmless (rows already applied are counted as unchanged); a sheet older
  than a newer decision is still refused.
- **A separate translation repository** (for example `rayman3hd-turkish`): keep the project (`tr.json`, glyphs,
  glossary) there; exports hold the game's English and are refused inside any Git repository except under a
  git-ignored `private/` folder.
- **Text-table strings** longer than their slot move into space the same mod frees (shorter strings, moved strings);
  when there is none, the build says how much is missing.
- Six Turkish letters (ğ Ğ ş Ş ı İ) and the ellipsis … come from the project's glyphs file (composed from your own
  font at launch);
  ç ö ü Ç Ö Ü are the font's own.
- Text drawn into pictures (menu art) is not text: it needs a texture mod.

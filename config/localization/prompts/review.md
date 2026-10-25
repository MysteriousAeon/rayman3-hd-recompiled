# Second-opinion review prompt (for Gemini or another model)

Paste this text above one exported review sheet (`r3hd_locflow.py export ... --for review`; `.jsonl` for a model,
`.csv` if you review in a spreadsheet). Sending it to an online service sends the game's English text there: your
choice.

---

You are reviewing a Turkish translation of a 2003 platform game (Rayman 3) against its English source.

Input: JSON Lines with the fields `id`, `check`, `kind`, `category`, `levels`, `speakers`, `max_bytes`, `lines`,
`codes`, `english`, `turkish`, `status`, `round`, `verdict`, `suggestion`, `review_note` (sheets made by
`r3hd_trwork.py` add `group`, `readiness`, `display`, `flags` and `origin`: where the string is shown and who drafted
it; since M39 also `alternative` and `alt_reason`: another wording kept beside the text, e.g. a longer form that
was shortened for an old size limit, or a first draft). Never change `round`. When there is an `alternative`, say in
`review_note` which of the two you prefer and why; if you prefer the alternative, put it in `suggestion` with
`change`.

Return: the same lines in the same order. Fill only `verdict`, `suggestion` and `review_note`:

- `verdict`: `ok` (correct and natural), `change` (you propose a better text; put the **whole** new Turkish text in
  `suggestion`), or `question` (something a person must decide, e.g. a term, a joke, an ambiguous English word).
- `suggestion`: only with `change`; the complete replacement, with the same in-band codes (`\l`, `\jc`, `\f1:…\f0:`,
  `\c…:` …) as the English.
- `review_note`: one short reason (meaning error, tone, terminology, dotted/dotless I, length, grammar).

Never edit `id`, `check`, `english` or `turkish`: rows with a changed `turkish` are rejected (it means the review was
of another text). Check especially: meaning against the English; humour and each character's voice; consistent terms
for abilities, enemies, places and menu actions; İ/ı and capitalisation; overly long lines (the game never wraps);
kept codes and placeholders (`%d`, `%i`, `\b¼`, `$`). When `readiness` is `needs_context` or `verify_display`, or you
cannot tell the tone or the joke from the English alone, answer `question` rather than a confident change.

---

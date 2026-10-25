# First-draft prompt (English → Turkish)

Paste this text above one exported batch (`r3hd_locflow.py export ... --for draft`, a `.jsonl` file). Sending the
batch to an online AI service sends the game's English text to that service: decide that yourself.

---

You are translating the in-game text of a 2003 platform game (Rayman 3) from English into Turkish.

Input: JSON Lines. Each line is one object with the fields `id`, `check`, `kind`, `category`, `levels`, `speakers`,
`max_bytes`, `lines`, `codes`, `english`, `turkish`, `note`. Batches made by `r3hd_trwork.py` add `group` (menu,
tutorial, dialogue, subtitle, …), `readiness`, `display` (where the string is shown, as far as known) and `flags`.

Return: the same JSON Lines, one object per input line, in the same order, with **only the `turkish` field filled**.

Rules:

1. Never change `id`, `check` or `english`. Never add, merge, split or drop lines. Rows whose `id` or `check` change are
   rejected on import.
2. Keep every in-band code exactly as written, in the same order where possible: `\l` (line break), `\jc` (centre),
   `\f1:`…`\f0:` (button glyphs, e.g. `\f1:3\f0:`), `\c255:255:255:` (colour), `\z…:`, `\hm…:`. The `codes` field lists
   the codes other than `\l`; the Turkish must contain the same ones. Do not translate or space them.
3. The game never wraps text. Keep roughly the English line lengths; use `\l` where the English has one (`lines` = how
   many lines the English has). `max_bytes` is the English slot size; a longer text may still fit, but shorter is
   safer. Movie subtitles (`kind` = subtitle) may be somewhat longer than the English (`max_bytes` 400 each), but
   keep them to one or two lines (`\l`) that can be read in the cue's time.
4. Use only characters the game can draw: Turkish letters (ç ğ ı İ ö ş ü and capitals), basic Latin letters, digits and
   ordinary punctuation. No emoji, typographic quotes, or special symbols that the English does not have.
5. Write natural, spoken Turkish that fits a humorous family game. Keep each character's tone (`speakers` is a code
   from the voice file, e.g. a four-letter abbreviation; it is a hint, not a name). Keep names (Rayman, Globox, …) as
   names unless told otherwise. Mind dotted İ / dotless ı in capitals.
6. If you are unsure, still give your best translation and put a short reason in `note` (not in `turkish`).
7. Keep placeholders exactly as often as the English has them: `%d`, `%i`, `%s`, the icon `\b¼`, `$`. Never put a
   Turkish suffix directly on a button code or a placeholder: write `\f1:c\f0: tuşuna bas`, not a suffix after the code.
8. `readiness` = `needs_context` or `verify_display` means nobody knows yet who says it or whether it is shown: do not
   invent a scene, speaker or tone; give a plain, neutral translation and say in `note` what context is missing.
   Do not assume sarcasm, humour or formality that the English alone does not show.
9. Follow the project's style guide and glossary when they are given with the batch (names stay names; suffixes on
   names with an apostrophe; menus in sentence case; the player addressed as *sen*).

---

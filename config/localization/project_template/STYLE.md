# Turkish style guide (Rayman 3 HD)

A working guide for drafts, reviews and decisions. Everything marked **proposed** is a starting point written with
the M37 tools, not a decision: the translator confirms or changes it, and records the decision in `glossary.json`
(`"status": "approved"`). The tools never overwrite an approved term or an approved string.

This file holds no game text. Examples are illustrative sentences, not lines of the game.

## 1. Names

- **Character names stay as they are** (proposed): Rayman, Globox, Murfy, André, Reflux, Begoniax, Razoff and the
  others. They are names, not words to translate.
- **Suffixes on names take an apostrophe** (TDK rule): *Rayman'ın*, *Globox'a*, *André'yi*. The vowel of the suffix
  follows how the name is **pronounced** in Turkish, not how it is written; when unsure, choose the form a Turkish
  player would say aloud and record it in the glossary note so that every string uses the same one.
- **Species, enemies and collectables** (Hoodlum, Teensies, lums, Knaaren, Leptys …) are an open decision: keep the
  name, or give a Turkish name. Decide once per term in the glossary before approving strings that use it; a
  half-translated set is worse than either choice.
  - A kept common noun is written in lower case and takes suffixes without an apostrophe when the game itself treats
    it as a common noun (*lumlar*, *kırmızı lumu*), with an apostrophe when it is a proper name.
- **World and level names** are proper names shown in menus and on the map: translate them as names (short, title
  form), consistently in the menu, the dialogue and the subtitles. Keep a glossary entry for each.
- **Abilities and moves** (punch, charged punch, helicopter, lock-on, look mode, photo mode …) appear in the
  tutorial, the controller-mapping screen and dialogue: one Turkish term each, the same everywhere.

## 2. Turkish letters, case and the I problem

- Dotted and dotless: **i ↔ İ**, **ı ↔ I**. In all-caps text write *İ* for i (*İPTAL*, *DEVAM ETMEK İÇİN*). The
  validator warns about a capital I inside an all-caps word.
- Never let a program change case with generic functions: `str.upper()` turns *i* into *I*, and `str.capitalize()`
  turns *İ* into *i* + a combining dot that the game cannot store. Change case by hand, or with a Turkish-aware
  function (the tools' `tr_upper` / `tr_lower`).
- ç ö ü Ç Ö Ü are in the game's font; ğ Ğ ş Ş ı İ come from the translation's glyph file. Do not use typographic
  quotes (“ ” ‘ ’), long dashes or emoji: the validator refuses characters the game cannot draw. Use straight quotes
  `"` and `'`.
- The apostrophe of a suffix is the straight `'` (Rayman'ın).
- **The game's font has no `;`, `<`, `>`, `{`, `}`** and no ellipsis character `…`: use a comma, a full stop or a
  colon instead of a semicolon, and `...` for an ellipsis. The tools refuse these characters when they can read
  your game data.
- `$…$` in the English are the game's quotation marks (around titles and quoted phrases): keep them in pairs.

## 3. Tone and address

- **Address the player as *sen*** (proposed): imperatives such as *Zıplamak için … bas.* Keep it the same in hints,
  menus and system messages. **Open decision:** the M34 sample mod (`config/localization/tr/tr.json`) used the formal
  *siz* in two confirmation boxes; the M37 drafts use *sen* throughout. Choose one before approving dialog boxes.
- **Menus: sentence case** (proposed): *Oyuna dön*, *Ayarları kaydet*, not English title case. Short labels may be a
  noun (*Ses*, *Görüntü*) or an imperative (*Kaydet*); keep one pattern per screen.
- **Characters' voices**: write natural spoken Turkish. Do **not** decide from a single line that a character is
  sarcastic, formal, childish or joking. The tools give a level and a speaker code for voiced lines and nothing more;
  a line without that is `needs_context`. Leave a note instead of forcing a tone, and fill the character notes below
  only from what you have seen or heard in the game.
- **Jokes, puns, wordplay, references**: translate what the line does (a pun, an insult, a parody), not its words. If
  you cannot tell what it refers to, give a plain translation, mark it with a note (`note` in a batch, `human_note` in
  a sheet) and leave it for a person who has seen the scene.
- **Mild language**: keep the game's level of rudeness; do not add or remove insults.

### Character notes (to be filled by the translator from the game, not guessed)

| speaker code | who | voice notes |
|---|---|---|
| | | |

## 4. Menu terminology (proposed)

| English | Turkish (proposed) | note |
|---|---|---|
| Start | Başla | |
| Continue | Devam | as a button; *Devam et* in a sentence |
| Load / Save | Yükle / Kaydet | |
| Back | Geri | |
| Cancel | İptal | |
| Yes / No | Evet / Hayır | |
| OK | Tamam | |
| Options | Ayarlar | *Yardım/Ayarlar* fits the main-menu slot (M34 sample, seen in game); *Seçenekler* is the alternative |
| Controls | Kontroller | |
| Audio / Video | Ses / Görüntü | |
| Subtitles | Altyazılar | |
| Vibration | Titreşim | |
| On / Off | Açık / Kapalı | |
| Exit Game | Oyundan çık | |
| Resume Game | Oyuna dön | |
| Loading | Yükleniyor | |
| Leaderboards / Achievements | Lider tabloları / Başarımlar | Xbox's own Turkish terms may differ: check them |
| Picture (photo mode) | Fotoğraf | |
| Level | Bölüm | |
| Score | Puan | |

Short instructions may use the compact form *Zıplamak için \f1:c\f0:.* when the full sentence (*… tuşuna bas.*) does
not fit the slot; keep one form per screen.

## 5. Codes, buttons and placeholders

- Copy every in-band code exactly: `\jc` (centre), `\f1:c\f0:` (a button glyph), `\c255:255:255:` (colour), `\z…:`,
  `\hm…:`. Only `\l` (line break) may move. The importers refuse a row whose codes changed.
- Placeholders `%d`, `%i`, the save icon `\b¼` and `$` markers must stay, as often as in the English (refused
  otherwise).
- **No suffix directly on a button glyph or a number placeholder**: the letter that decides the suffix is not known.
  Write *\f1:c\f0: tuşuna bas*, *%d KB boş alan*.
- Leading spaces in a string are layout: keep them unless you know the box.

## 6. Length, line breaks and subtitles

- **The game never wraps text.** A line drawn wider than the English by more than 15 % is a warning; break with `\l`
  or shorten. Keep the English line count unless you know the box fits more.
- Table strings longer than their slot are moved by the build when the mod frees room elsewhere; the build says when it
  cannot.
- **Subtitles**: one or two lines (`\l`), readable in the cue's time (as a rule of thumb, about 15–17 characters per
  second); timing cannot change. At most 400 bytes each; the table may grow since port 0.36.0.
- Centred boxes (`\jc`) with several lines: keep lines of similar length.

## 7. Review and approval

- A model's draft is a **draft**; a second model's opinion is a **review**; only the person's decision sheet makes a
  string **approved**. A 100 % drafted project is not a finished translation.
- Reviewers put a whole replacement in `suggestion` and a reason in `review_note`; they never edit the Turkish
  column. Use `question` for anything a person must decide (a term, a joke, an unknown context).
- Record every terminology decision in `glossary.json` with `"status": "approved"` before approving the strings that
  use it.

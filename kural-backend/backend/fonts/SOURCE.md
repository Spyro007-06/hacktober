# Bundled font: Noto Sans Tamil

Used for Tamil text in generated PDFs (the PRD requires Noto Sans Tamil, p.5).

| Item | Value |
|---|---|
| File | `NotoSansTamil[wdth,wght].ttf` (variable font, used **unmodified**) |
| Version (font name table) | Version 2.004 |
| Copyright | Copyright 2022 The Noto Project Authors (https://github.com/notofonts/tamil) |
| Licence | SIL Open Font License 1.1, full text in `OFL.txt` (kept with the font as the licence requires) |
| Reserved Font Name | None declared in `OFL.txt` (the text only defines the term) |
| Source repository | https://github.com/google/fonts, directory `ofl/notosanstamil` |
| Pinned commit | `8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5` (2026-03-12; newest commit touching that directory) |
| Download URL | `https://raw.githubusercontent.com/google/fonts/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/notosanstamil/NotoSansTamil%5Bwdth%2Cwght%5D.ttf` |
| Retrieved | 2026-10-26 |
| Size | 340,668 bytes |
| Git blob SHA-1 | `cb08d499b2d05ef6fd8e470c36c2be47ff368f0d` (matches the value GitHub's contents API reported for that commit) |
| SHA-256 | `aa3a9b321f4b0bb2c40203ffbde9af89713227866e0e13f76e5b9eeea727cf88` |

`OFL.txt`: 4,381 bytes, git blob SHA-1 `677d559b94ba7c63d41a7bf6ffa0a3eb11f2de95`,
SHA-256 `f8ff8ce7d0a81bf8d5e121c635ef027250c531f2fd37d5988b8dd6e45f19d7f1`,
same repository, directory and commit.

## What was checked

- Size and git blob SHA of both files matched the values read from the GitHub API before downloading.
- The font parses as a TrueType font (fontTools): 576 glyphs, `fvar`, `GSUB` and `GPOS` tables.
- Axes: `wght` 100-900 (default 400), `wdth` 62.5-100 (default 100); named instances Thin to Black.
- 72 code points of the Tamil block (U+0B80-0BFF) are mapped, including the vowel signs, virama,
  grantha letters, aytham and Tamil digits used by split vowels and conjuncts.

## What has NOT been checked

- Rendering through WeasyPrint/Pango (variable-font weight handling, shaping, embedding).
  Do not treat Tamil PDF output as verified until that has been looked at.
- There is no vendor signature for this file; integrity rests on the repository's own hashes.

## Notes

- The file name contains `[`, `]` and `,`. PowerShell treats `[...]` as a wildcard unless you
  use `-LiteralPath`.
- To update: pick a new commit, repeat the size and blob-SHA checks, and update this file.

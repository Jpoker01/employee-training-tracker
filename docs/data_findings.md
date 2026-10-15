# Data findings

Verified against the raw exports (export date 2026-10-01). Record IDs only, no personal values.
Status: `open` = decision pending, `decided` = rule agreed, `HR?` = candidate question for HR (deadline 2026-10-19).

## Notebook review (exploratory_ntb.ipynb)

- Bug, cell 43: completions store names as "Prijmeni Jmeno", the check builds "jmeno prijmeni" -> 2856 false mismatches. Use `prijmeni + " " + jmeno`.
- Cell 55 parses ISO dates only; T014 (`31. 9. 2026`) silently becomes NaN.
- `value_shapes` masks ASCII letters only, so `Kč` shows as `Ač`.
- `requirements.txt` is unpinned; needs `pandas>=2.3.3` for Python 3.14.

## absolvovana_skoleni.csv (cp1250, `;`)

- Junk rows: a comment line (`# export z 1. 10. 2026 - doplněno ručně, nezapočítávat ...`, row 607), a repeated header (row 1591), the `Celkem` footer, 2 empty rows. 2868 parsed rows vs 2865 real records. Filter: `id_zaznamu` matches `Z\d{6}`. `open`
- Date formats: `2019-01-06`, `6. 1. 2019`, `06.01.2019`, plus 3 Excel serial numbers (Z000471, Z000623, Z001510; origin 1899-12-30). `open`
- Placeholder dates `1900-01-01` (Z000001, Z000002). `open`
- 5 records dated after the export date, all `zadáno předem` (e.g. Z002836-Z002840). Must not count as completed. `HR?` registrations or something else?
- `platnost_do` disagrees with catalog validity in some rows (e.g. Z000099 PRV-POM 4 years vs 36 months); 49 rows have empty `platnost_do`. Size of the disagreement not measured yet. `HR?` which source wins?
- 15 duplicate `id_zaznamu`: same record written twice, often in two date formats (e.g. Z000052). Deduplicate after parsing dates. `open`
- Records for unknown employees E9001-E9009 (`Neznámý Zaměstnanec`). Exclude and report. `open`
- Code variants: leading/trailing spaces, lowercase, `POZ_OCH`, `POZ OCH`, `BOZP_Z`. Normalise with strip + upper + `[_ ]` -> `-`. Unknown after that: `BOZP-X`, `GDPR-2`, `KYB3R`. `open`
- Provider names in mixed case. Cosmetic.
- Prices: `zdarma`, negatives, `450,- Kč`. Not needed for the task; report only, do not parse. `decided`
- Multi-line quoted notes parse correctly.

## zamestnanci.csv (utf-8-sig, `,`)

- `rodne_cislo` on all 174 rows. Dropped right after loading. `decided`
- `stav`: aktivní 156, ukončen 12, rodičovská 6. `HR?` are people on parental leave in scope?
- 4 active employees with a future `datum_ukonceni` (E0009, E0020, E0047, E0134; Jan-Mar 2027). `HR?` still schedule them?
- `utvar` variants: `Laboratore`, `SPRÁVA BUDOV`, `správa budov`, `Sprava budov`, `Studijní`, `Studijni oddeleni`, `Personalni oddeleni`, `VEDENÍ`; 5 empty. Matters for PRV-POM and LAB-BEZ (assigned by department). `open`
- Likely duplicate people: E1000 = E0155, E1002 = E0124 (same email, name without diacritics); E1001 and E1003 have `...2@` emails, same pattern. `open`
- 8 malformed emails (embedded space, `@vzorova,example`, missing domain): E0002, E0099, E0121, E0129, E0150, E0157, E1001, E1003. `open`
- 3 employees with manager `nezname.jmeno@vzorova.example` (E0023, E0080, E0097).
- Formula-injection payloads in `poznamka` (E0066, E0069, E0108, E0153: `-2+3`, `@SUM(1+1)`, `+1+1`, `=HYPERLINK(...)`). Any CSV/Excel export must neutralise them; HTML output must be escaped. `decided`
- `datum_nastupu`: mostly ISO, 5 rows `d. m. yyyy`.

## katalog_skoleni.csv (utf-8-sig, `,`)

- `platnost_mesicu`: `24`, `2 roky` (ZDVIH), `0` (LEAD), empty (ANGL). `HR?` LEAD `0` = one-off?
- `povinne_pro` grammar: `VSICHNI`, `UTVAR:a;b;c`, `POZICE:x`, `NEPOVINNE`.

## terminy_skoleni.csv (utf-8-sig, `;`)

- Past terms relative to export: T019, T008, T022. Cancelled: T017, T028.
- `KYB3R` typo (T010). Invalid date `31. 9. 2026` (T014). Capacity 0 (T026).
- Overbooked: T016 (31/30), T030 (21/20).
- T003 and T009 identical (same date, place, capacity, booked). `open`
- Prices: `2 100 Kč`, 2 empty. Not needed. `decided`
- `obsazeno` gives counts only, not who is registered. `HR?` link to `zadáno předem` records?

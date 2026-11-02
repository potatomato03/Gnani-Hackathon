# Formulary sources

`products.csv` will hold about 100 hand-checked rows. A row is only marked `verified` after a person checks it against a named source.

| Source | Licence | Checked on | Used for |
|---|---|---|---|
| Indian Medicine Dataset (junioralive) | MIT on the repo, data origin not stated | | Brand, composition and strength lookup |
| IndianDrugMCQA (Eka Care) | MIT | | Brand to generic cross-check |
| Jan Aushadhi product list | Reproduction needs emailed permission and credit | | Local cross-check of generic names |
| NLEM 2022 | No licence stated | | Choosing common generics |

Raw files are in `DATA/formulary/`, outside this repo. See [DOWNLOADS.md](../DOWNLOADS.md). Each row records its source, the person who checked it and the date.

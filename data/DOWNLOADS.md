# Downloaded data

Third-party data doesn't go in this repo. It lives in a `DATA` folder next to the repo, at `../DATA`, and takes about 5 GB. To set it up, copy the folder from a teammate or download each item from the links below, then check it against the checksums.

These are raw inputs. Anything we check or build from them goes in `data/`.

## What's in DATA

| Folder | What it is | Version | Licence | Use |
|---|---|---|---|---|
| `formulary/indian_medicine_dataset/` | 253,973 Indian products with manufacturer and composition | [Commit 7c06a88](https://github.com/junioralive/Indian-Medicine-Dataset/tree/7c06a889dc949d3b6a9be28c448f4aa1e7a2848f) | MIT on the repo, data origin not stated | Lookup. Hand-check every row we keep. |
| `formulary/indian_drug_mcqa/` | 1,512 brand-to-generic questions, 1,092 brands | [Commit 483c8fe](https://huggingface.co/datasets/ekacare/indian_drug_mcqa/tree/483c8fe618570851859f08e288aaa09cc6046298) | MIT | Cross-check only |
| `formulary/jan_aushadhi/` | Official list of 2,445 products with MRP | [Exported 2026-11-02](https://janaushadhi.gov.in/product-portfolio/product-mrp-list) | Reproduction needs emailed permission and credit | Local cross-check of generic names |
| `formulary/nlem_2022/` | National List of Essential Medicines 2022 | [CDSCO PDF](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadConsumer/nlem2022.pdf) | No licence stated | Choosing common generics |
| `noise/rirs_noises/` | 843 noise recordings from MUSAN (806 foreground, 37 background), plus real and simulated room responses, 16 kHz | [OpenSLR SLR28](https://www.openslr.org/28/) | Apache 2.0; MUSAN is CC BY 4.0 | Noise and reverb for noisy audio variants |
| `fhir/abdm_ig/` | ABDM FHIR guide package, OPConsult and Prescription examples | [v6.5.0, FHIR 4.0.1](https://www.nrces.in/ndhm/fhir/r4/StructureDefinition-DocumentBundle.html) | CC0-1.0 | Validating our bundles |
| `knowledge/openfda_label/` | openFDA drug labels: 262,903 US labels in 14 zipped JSON files, 1.77 GB | [Export of 2026-10-30](https://api.fda.gov/download.json); `manifest.json` beside the files holds each file's size and SHA-256 | CC0 1.0 ([openFDA terms](https://open.fda.gov/terms/)) | Medicine knowledge chunks. Download with `tools/knowledge/download_openfda_labels.py`. |
| `knowledge/chunks/` | Built, not downloaded: medicine knowledge chunks from openFDA, NLEM and Jan Aushadhi | `tools/knowledge/build_chunks.py` | Each chunk carries its source's licence | Retrieval. Kept here because the Jan Aushadhi and NLEM text can't go public. |
| `optional/aci_bench/` | 207 English doctor-patient conversations with notes | [Commit b909b2b](https://github.com/wyim/aci-bench/tree/b909b2bb9cf1d19de08df15cddde7bd0179665e4) | CC BY 4.0 | Optional outside check, after the core |

## Models

Models live in `../models`, next to `DATA` and the repo.

| Folder | What it is | Version | Licence | Use |
|---|---|---|---|---|
| `models/faster-whisper-large-v3/` | Whisper large-v3 for faster-whisper, 3.09 GB | [Commit edaa852](https://huggingface.co/Systran/faster-whisper-large-v3/tree/edaa852ec7e145841d8ffdb056a99866b5f0a478) | MIT | Free local transcription while building the pipeline. Never report its results as Prisma's. |
| `models/fastembed/` | `BAAI/bge-base-en-v1.5` as Qdrant's ONNX build (`Qdrant/bge-base-en-v1.5-onnx-Q`), 208 MB, fetched by fastembed 0.9.1 | Snapshot `199291fdd1aa89faf9c20b722dc72ad5e17aa0d0` | MIT | Embedding the medicine knowledge chunks (runbook D-101) |

Whisper `model.bin` SHA-256: `69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`

bge-base `model_optimized.onnx` SHA-256: `4e556722bc4f65716c544c8a931f1e90fb3f866e5741fd93a96f051d673339c7`

## Limits

- **Side-effect and interaction text:** `updated_indian_medicine_data.csv` has these columns, with no stated source. Never use them for drug cards.
- **Discontinued products:** 7,905 rows are marked discontinued. Filter them out.
- **Zero MRP:** 345 Jan Aushadhi rows have zero MRP, which the site says means under process.
- **Jan Aushadhi:** email PMBI for permission before reproducing this list anywhere public, and credit the source.
- **ACI-Bench:** it's US English with no Indian brands, and some speaker tags are swapped.
- **openFDA labels:** US labels state US-approved uses and doses. Medicines sold only in India (domperidone, methylcobalamin, ornidazole, aceclofenac on its own) have no US label. 182,206 of the 262,903 labels carry no active-ingredient data (mostly unapproved and homeopathic products) and are skipped. Copyrighted text supplied by companies can sit inside labels; the openFDA terms say it may not be public domain.

## Not downloaded

| Source | Why |
|---|---|
| MUSAN full set | 11 GB, and its noise files are already in RIRS_NOISES |
| PriMock57 | Real voices. Ask Gnani first. |
| Synthetic Medical Dictation | Method reference only |
| DISPLACE-M, IndicVoices, Eka Medical ASR | Real people's speech, see `data/README.md` |
| National Formulary of India | Paid edition, and no reuse terms found |

Case specs, scripts, gold notes, drug cards, rules and agent questions can't be downloaded. We build them in `data/`.

## Checksums

SHA-256, relative to `DATA/`. The openFDA files are listed in `knowledge/openfda_label/manifest.json`.

```
c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042  formulary/indian_medicine_dataset/indian_medicine_data.csv
1032846aa3e96db07631d1229ec3ec364e03cd505c1dcbd094f1ecd3f3fe75f5  formulary/indian_medicine_dataset/updated_indian_medicine_data.csv
a39b94a52f4849c57e42f68009346f012a7e7e42e8ab5c34e75662c8c987c647  formulary/indian_drug_mcqa/test-00000-of-00001.parquet
4ac1c0e8967e16de86aad74b0810fc06342d5f81bbe3e27bb7c6e5d46e02c4d3  formulary/jan_aushadhi/jan_aushadhi_product_list_2026-11-02.csv
17dfa27760a73cee226392109a4e96f2594921431cfd6b7a8acfe8eab5e01533  formulary/nlem_2022/nlem2022.pdf
3b50cfde915b3984738169b4beb341e9f6b8062ae4c2076146c5db71c2c05dc7  noise/rirs_noises/rirs_noises.zip
41fa99955adbd1983a235d7c7136b30f423ce34ff541d86b354d95b7704527d4  fhir/abdm_ig/package.tgz
ee55812516a81fe9e0a1a735fbbc099ea94fdf998777e0c73c5a8b017acc5642  fhir/abdm_ig/Bundle-OPConsultNote-example-05.json
773f331773e8eb41a7e515770dbda1889ee55288886a061a2d9d04613b90f1dc  fhir/abdm_ig/Bundle-Prescription-example-06.json
73b94326cbf8967b08203a6a4cc22a3ceb15bce27f8fc9677729d3f5f2b5d0e4  optional/aci_bench/aci-bench-b909b2bb9cf1d19de08df15cddde7bd0179665e4.zip
```

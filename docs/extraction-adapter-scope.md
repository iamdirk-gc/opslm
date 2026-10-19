# Extraction Adapter: Scope (board tasks 2.1-2.3)

Status: scoping, 2026-10-18. Nothing here is built. The adapter turns source documents into the
facts and documents that the pair miner ([pair-mining.md](pair-mining.md)) consumes, so it is the
last missing link on the critical path to the real holdout set. Decisions that need the project
owner are collected in [decisions.md](decisions.md); the ones this scope depends on are D-01 to D-06.

## 1. The contract

The adapter's output is exactly what the rest of the repo already reads:

- `documents.jsonl`: one `SourceDocument` per input file (`doc_id`, `company`, `document_family`,
  `doc_type`, `title`, `source_url`, `retrieved_at`, `content_sha256`, `license_note`).
- `facts.jsonl`: one `BusinessFact` per extracted number, schema v0.2.0.

Nothing downstream changes. `python -m opslm.mining_cli --facts facts.jsonl --documents
documents.jsonl` then produces candidates for labeling.

| `BusinessFact` field | Comes from | Method | Main failure mode |
|---|---|---|---|
| `metric_label` | The row header or the sentence naming the number | Text of the cell or phrase, verbatim | Wrong row when headers span rows or sub-rows nest under segments |
| `metric_id` | Mapping of the label | Rules from the metric page, `other` when unmatched | A near-miss label mapped to a v1 metric ("Core revenue" must stay `other`) |
| `entity` | Company in the document header; segment headings above a block of rows | Rules; `None` when not stated | Calling a segment table "consolidated" |
| `period` | Column headers, table captions, slide titles | Header parser (FY, quarter, LTM, "year ended ...", as-of dates) | Fiscal vs calendar; decks that give no dates (the schema allows `None` dates) |
| `quantity` | The cell or phrase | Number parser: parentheses and minus signs, scale and currency from captions ("in thousands"), percent | Scale stated once at the top of a table and missed; sign conventions |
| `accounting_basis` | Section headings ("Non-GAAP", reconciliation tables), the metric itself (Adjusted EBITDA is non-GAAP) | Rules | Marking a non-GAAP table GAAP |
| `reporting_status` | Document type (10-K statements audited, 10-Q and decks unaudited) | Rules from `doc_type` | Audited line items inside an unaudited document |
| `stated_definition` | Footnotes, glossaries, "we define ... as" sentences near the label | Text search; the definition sentence is also added to the fact's evidence so it can be cited | Definitions several pages away or only in a different document |
| `evidence` | The cell or phrase | Page, table id, cell reference (or character offsets) plus the verbatim text | Provenance the parser does not expose (see section 4) |
| `extraction` | The adapter | Extractor name and version, optional confidence | n/a |

**Sign normalization (decision D-05).** The recommendation is that the adapter normalizes sign
(a loss is stored negative, whatever the printing) and keeps the printed form in `raw_text`, so
the reconciler compares signed values. This is already how the schema and the generator behave.

## 2. Architecture

```
manifest (owner's task 2.2) --> Parser (swappable) --> parsed tables and text
   --> number, header and caption parsers --> fact candidates
   --> metric mapping --> scope resolution (entity, period, basis, status)
   --> definitions --> validation --> facts.jsonl + documents.jsonl
```

- **Parser behind an interface.** `Parser.parse(path) -> ParsedDocument` (pages or sheets, tables as
  grids of cells with row and column spans, text blocks, each with a location). The adapter's own
  logic works on `ParsedDocument`, never on a vendor's objects, so Docling, Azure Document
  Intelligence and Google Document AI are interchangeable (board task 2.1: "kept swappable behind
  an interface").
- **Parser-independent layers** hold most of the work and can be built and tested now with no
  documents: number parsing, period and caption parsing, metric mapping, and validation.
- **Validation** reuses the miner's `supported()` check (does the evidence text contain the
  printed number?) so wrongly attached evidence is caught for free.

Proposed entry point (not built):

```bash
python -m opslm.extract --manifest manifest.jsonl --parser docling --out-dir data/extracted/
```

### The manifest (the owner's task 2.2 deliverable)

One row per source document, as a CSV or JSONL the owner can produce from a spreadsheet:

| Column | Example |
|---|---|
| `doc_id` | `acme-10k-fy2025` (company slug, document type, period) |
| `company` | `Acme Software Inc.` |
| `document_family` | `acme-fy2025` (one company and filing period; the unit the splits keep together) |
| `doc_type` | `10-K`, `10-Q`, `earnings_deck`, `investor_presentation`, `workbook` |
| `source_url` | where it was retrieved |
| `retrieved_at` | date |
| `license_note` | redistribution terms, or blank until decided (D-02) |
| `local_path` | where the file is on disk (never committed; see D-02) |

The adapter computes `content_sha256` itself.

## 3. Approach by document type

| Type | Share of the work | Notes |
|---|---|---|
| Spreadsheets (investor-relations financial supplements) | Easiest | Cells have exact coordinates; headers are usually one or two rows. Public filings rarely include workbooks, but many SaaS companies publish a historical-financials workbook |
| 10-K and 10-Q (HTML or PDF) | Medium | Table-heavy and regular. SEC filings are HTML with inline XBRL tags, which carry machine-readable values, periods and entities (see D-04) |
| Earnings decks and investor presentations (PDF, PPTX) | Hardest | Few tables, numbers in bullets and charts, no dates, and often no definitions. The decks are where ARR and Adjusted EBITDA live, and where "insufficient evidence" cases come from |

Charts and images are out of scope. Scanned documents need OCR and are out of scope for the
first cut.

## 4. Choosing the parser (task 2.1)

Candidates, with what is known:

| | Docling | Azure Document Intelligence | Google Document AI |
|---|---|---|---|
| License and hosting | MIT code, runs locally and air-gapped (verified from the project README); individual model licenses apply | Hosted service, per-page pricing | Hosted service on Google Cloud (fits the existing GCP project), per-page pricing |
| Inputs | PDF, DOCX, PPTX, XLSX, HTML, images (verified) | PDF and images (office formats need conversion; not verified here) | PDF and images (not verified here) |
| Output | A unified document model with tables, reading order and provenance; lossless JSON export (verified) | Layout JSON with tables | Layout JSON with tables |

**Not verified from public documentation, and to be confirmed in the spike:** how Docling
represents table cells (spans, header flags), what provenance a spreadsheet cell gets (a third-party
mirror says each worksheet is treated as a page, with no mention of cell coordinates), install size
and runtime on the M2, and the hosted services' table accuracy on financial statements.

**Recommendation to test, not a conclusion:** Docling first, behind the interface. It is local,
free, handles every input type in scope, and keeps public documents off third-party servers. Run a
hosted parser on the same documents only if Docling misses the bar below.

**The spike (1 to 2 days, before committing to anything):** three documents (one table-heavy 10-K,
one investor deck, one workbook), and 30 target numbers read by hand from them. For each parser,
measure:

1. Cells recovered with the right text, row header and column header (target: at least 90% of the
   30).
2. Whether provenance is good enough to fill an `EvidenceSpan` (page, table, cell or character
   offsets).
3. Install size, runtime per document, and cost.
4. Failure modes, written down: merged headers, scale captions, footnote markers.

## 5. How extraction quality will be verified

Extraction errors poison every downstream number, so this is not optional:

1. **Round-trip tests.** Render synthetic scenarios (the generator already knows the true facts) to
   a workbook and to HTML, run the adapter, and compare. This catches regressions in the number,
   header and mapping logic with exact ground truth. It does not prove the adapter works on real
   documents.
2. **A hand-verified sample.** The owner or engineer verifies about 60 extracted facts across the
   real document set against the source (value, scale, period, entity, basis). Target: at least 95%
   correct on the core metrics from tables (D-06 sets the bar and who does it).
3. **Free automatic checks.** `supported()` on every fact; counts of facts per document and metric
   (a 10-K with no revenue fact is a miss); and, for SEC filings, cross-checking against the XBRL
   value where one exists.

Fact-level precision and recall against the verified sample are reported with the benchmark, as a
separate result from reconciliation accuracy (board task 4.1 asks for both modes).

## 6. Work breakdown

Estimates are engineering days for one person, with test-writing included.

| # | Piece | Needs documents? | Days | In the MVP? |
|---|---|---|---|---|
| W0 | Parser spike and decision | Yes (3 documents) | 1-2 | Yes |
| W1 | `Parser` interface, manifest reader, `SourceDocument` builder (hashes, ids), CLI skeleton | No | 1 | Yes |
| W2 | Number parsing and normalization: parentheses, minus, scale and currency from captions, percent, sign | No | 1.5 | Yes |
| W3 | Period and caption parsing: FY, quarter, LTM, "year ended ...", as-of dates; entity and segment rules | No | 2 | Yes |
| W4 | Spreadsheet tables to facts | Yes | 1-2 | Yes |
| W5 | PDF and HTML financial-statement tables to facts | Yes | 3 | Yes |
| W6 | Metric mapping from the metric page, unmatched labels to `other` | No | 1 | Yes |
| W7 | Definitions, accounting basis and reporting status | Yes | 2 | Minimal: basis and status by rule, definitions by text search |
| W8 | Deck facts (numbers in bullets and short tables) | Yes | 3 | Only for ARR and Adjusted EBITDA |
| W9 | Verification: round-trip tests, the hand-verified sample, error analysis | Yes | 2 | Yes |

Total about 17-19 days; the MVP (W0 to W6, minimal W7, targeted W8, W9) is about 12-14 days.
**W1, W2, W3 and W6, about 5.5 days, need no documents and can start immediately**, while the
document set (D-01) and the licensing question (D-02) are being settled.

## 7. Schedule reality

The board has the adapter due Oct 17 and the release on Nov 9, 22 days from today. With the
dependencies above, an honest plan is in [status.md](status.md): the adapter MVP is the critical
path, fine-tuning (phase 5, already a stretch on the board) does not fit, and the release is
reachable only if the MVP scope is agreed (D-03) and the document set is chosen this week.

## 8. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| Decks yield few usable facts | Few "insufficient evidence" and company-defined cases from real data | Accept that synthetic data covers them for training; mine decks only for ARR and Adjusted EBITDA; weight the holdout toward 10-K and workbook pairs |
| Parser provenance does not reach cell level | Evidence spans are page-level only | Fall back to character offsets or table id plus row and column; record the limitation |
| Real `metric_id` and period fields are noisier than synthetic | The miner's strata are misassigned | The verification sample measures this; the report lists unsupported facts |
| Licensing blocks publishing the documents or their text | The holdout cannot be released as is | D-02 now: store references and hashes, keep raw documents out of the repo |
| Docling's dependency footprint on the M2 | Slow installs and runs | Measured in the spike; the interface allows a hosted parser |
| Scope creep into narrative extraction | The schedule slips | The MVP excludes it; revisit after the holdout is labeled |

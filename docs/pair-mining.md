# Pair Mining

`python -m opslm.mining_cli --facts facts.jsonl --documents documents.jsonl --out candidates.jsonl --report report.json`

Turns a corpus of extracted facts into a set of **unlabeled candidate pairs** for the labeling
workflow ([labeling-workflow.md](labeling-workflow.md)). Board task 3.2. It is what stands between
the extraction step (2.3) and labeling 100-200 held-out cases (3.4).

A random sample of pairs would be mostly unrelated facts or easy matches. The miner instead looks
for the pairs worth a human's time, with the subtle negatives the benchmark needs.

## Input

What the extraction step produces, one JSON object per line:

- `facts.jsonl`: `BusinessFact` records (schema v0.2.0), each with its evidence spans.
- `documents.jsonl`: `SourceDocument` records for every `doc_id` the facts cite.

The corpus is checked on load: every cited document must exist, fact and document ids must be
unique, and a fact's evidence must all come from one company.

For a dry run before real extraction exists, `--synthetic N` mines a corpus built from N synthetic
scenarios.

## How pairs are found

1. **Blocking.** Facts are paired only within one company, and only within a metric family (the
   metric id, or the normalized label when the id is `other`) or between families the
   [metric page](metric-set-v1.md) lists as related, so a corpus of thousands of facts does not
   mean millions of pairs. By default the two facts must come from different documents
   (`--allow-same-document` lifts that).
2. **Qualified variants.** A fact the extraction could not map to a v1 metric but whose label
   contains one ("Core revenue", "Constant currency revenue") is linked to that metric. These are
   not on the page, and they are exactly the pairs where a lookup fails.
3. **Strata.** Each pair gets the first stratum it matches:

| Stratum | A pair of facts with the same metric unless noted, where... | Typically surfaces |
|---|---|---|
| `unsupported_claim` | a fact's evidence text does not contain its printed number | extraction errors, insufficient evidence |
| `company_defined_definition` | ARR or Adjusted EBITDA, same scope, and the definitions are missing or differ | insufficient evidence, different concepts |
| `missing_scope` | an entity or a period is not stated | insufficient evidence |
| `same_metric_other_basis` | same entity and period, GAAP vs non-GAAP | related but different |
| `same_metric_other_period` | same entity, different period | related but different |
| `same_metric_other_entity` | different entity, segment or consolidation scope | related but different |
| `same_metric_same_scope` | same entity and period | equivalents and conflicts |
| `related_metric` | different but related metrics (revenue and ARR, gross margin and gross profit, ...) at the same entity and period | related but different |

A stratum records **why a pair was picked, not its label**. Humans label.

## Sampling

- A **quota per stratum** (`--weight stratum=w` to change; defaults favor hard cases: 30% likely
  matches, 20% related metrics, 13% company-defined, 10% each missing scope and other period, 7%
  other entity, 5% each other basis and unsupported claims). A stratum that cannot fill its quota
  hands the remainder to the heaviest others, and the report records the shortfall.
- **No company supplies more than 25%** of the target (relaxed when there are few companies), and
  **no fact appears in more than 3 pairs**, so a few filings do not dominate.
- Within a stratum the choice is a deterministic hash shuffle, so a run is reproducible for a seed.
- Pair order (which fact is A) is randomized the same way, so position carries no information.

**Do not read base rates off a mined set.** The mix is deliberate, so the share of conflicts or
abstentions in it says nothing about how often they occur in a real data room.

## Splits

**Planned change:** the project has fixed company roles (9 holdout companies whose pairs belong to
the test split only, 6 pattern sources that may supply training pairs). The miner currently assigns
by hash and will take the roles from the manifest instead.

Every pair of a company goes to one split, assigned deterministically by company
(`--fractions train validation test`, default 0.5 / 0.1 / 0.4), so company-level and
document-family leakage cannot occur and the dataset loader's checks hold by construction. Every
split with a non-zero fraction gets at least one company when there are enough.

## Output

- `candidates.jsonl`: `CandidatePair` records with tags `mined` and the stratum. Feed it to
  `python -m opslm.labeling_cli plan`.
- `report.json`: parameters, corpus counts, pairs available, per-stratum quota, availability,
  selection and shortfall, per-company and per-split counts, and the facts whose evidence does not
  contain their number.

## Checked against synthetic data

On 400 synthetic scenarios (labels ignored by the miner) it finds 517 of the 518 pairs the
generator labeled. Its strata line up with the labels: every pair in the other-period,
other-basis and other-entity strata was related but different, every missing-scope pair was
insufficient evidence, and 76% of related-metric pairs were related but different (most of the
rest are qualified variants such as "Core revenue" with no definition, which are insufficient
evidence, as intended). That check is in the test suite
(`tests/test_mining.py`). It does not say how the miner behaves on real extraction output.

## Limitations

- **Untested on real extraction.** It has only seen synthetic facts. Real output will have noisier
  metric ids, periods and entities, and the strata are only as good as those fields.
- **The relation table is the metric page.** Related metrics not on the page, and labels that
  contain none of the keywords, are not paired. The keyword rule is loose ("Revenue per employee"
  is read as a qualified variant of revenue), so expect some noise that labelers discard.
- **`unsupported_claim` is a text search.** It catches a number missing from the evidence, not a
  wrong number in the right sentence.
- **Company-level splits on a small corpus are lumpy.** With 10-20 companies, which ones land in
  test matters; change `--seed` for a different draw.
- It pairs two facts at a time. Clusters of three or more facts are not built.

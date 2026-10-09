# OpsLM: Open-Source Data Harmonization & Model Evaluation Toolkit

## 1. Final Product: What We're Building

An open-source toolkit that helps companies evaluate, fine-tune, and deploy smaller, specialized AI models to identify, normalize, and reconcile inconsistent business data across documents.

Initial use case: financial and business data rooms containing financial statements, spreadsheets, contracts, presentations, and other business documents.

The toolkit will include:

- **Evaluation framework:** Benchmarks semantic matching, reconciliation accuracy, false matches, evidence traceability, latency, and cost across rules-based systems, frontier LLMs, and open-weight models.
- **Fine-tuned open-weight model:** A specialized model for identifying equivalent business concepts, resolving inconsistencies, and detecting conflicting information.
- **Synthetic data generator:** Creates realistic, labeled examples of inconsistent and ambiguous business information for training and testing.
- **Reusable pipeline:** Integrates with existing document extraction tools and supports configurable business taxonomies and data models.

**Goal:** Build a reusable AI component that companies can integrate into existing document processing and enterprise data workflows, while providing a rigorous way to determine which modeling approach delivers the best quality, reliability, and cost.

## 2. Business Problem

Companies regularly process large volumes of inconsistent, overlapping, and unstructured information spread across documents and systems. A data room may contain hundreds or thousands of files reporting similar information using different terminology, formats, definitions, and reporting periods.

Example:

| Document | Reported information |
|---|---|
| Financial statements | FY2025 Revenue: $42.5M |
| Management presentation | FY2025 Sales: $44.1M |
| Revenue workbook | FY2025 Net Revenue: $42.5M |
| Investor presentation | FY2025 ARR: $39.2M |

Existing extraction tools can identify these values, but they don't necessarily establish whether the underlying business concepts are equivalent, whether differences are explainable, or whether the information conflicts.

Why this matters:

- **High volume:** Thousands of data points may need to be compared and reconciled.
- **High cost:** Repeated use of large general-purpose models can generate substantial inference costs.
- **Data quality:** Incorrectly merging different concepts propagates errors into downstream analysis.
- **Manual effort:** Analysts spend time standardizing terminology, resolving discrepancies, and verifying information.

The opportunity extends beyond data rooms to financial reporting, insurance, compliance, and enterprise data integration.

## 3. Proposed Solution

Rather than building another OCR or document extraction product, OpsLM leverages existing extraction technologies and specializes in semantic data harmonization and model evaluation.

Architecture:

```
Documents and spreadsheets
  -> Existing extraction tools (Docling, Azure Document Intelligence, Google Document AI, etc.)
  -> Structured business facts with source references
  -> OpsLM semantic reconciliation layer
       - Rules-based baseline
       - General-purpose LLM
       - Open-weight model (base and fine-tuned)
  -> Deterministic validation and evidence tracking
  -> Canonical, evidence-linked data model
  -> OpsLM evaluation framework: accuracy, false matches, evidence, latency, and cost
```

The initial task is to determine the relationship between two extracted business facts, considering their definitions, reporting periods, entities, units, values, and source context.

Possible outputs: **equivalent**, **related but different**, **conflicting**, or **insufficient evidence**.

The system preserves original sources, distinguishes semantic equivalence from numerical agreement, and avoids forcing matches when evidence is insufficient. Fine-tuning will be evaluated against simpler alternatives rather than assumed to be the optimal approach.

## 4. Core Steps to Build

1. **Define the data model and initial task.** Create a canonical business-fact schema covering metric, value, entity, period, units, definition, and source reference. Start with a narrow set of financial and operating metrics.
2. **Integrate existing extraction tools.** Use an established parser to extract information from PDFs and spreadsheets while retaining source locations and metadata. Avoid building a custom OCR pipeline.
3. **Create training and evaluation datasets.** Combine public financial documents with synthetic examples of equivalent, conflicting, and ambiguous information. Build a carefully reviewed, held-out evaluation set with scenario-level separation from training data.
4. **Establish model baselines.** Evaluate deterministic rules, a general-purpose frontier LLM, and an untuned small open-weight model on the same reconciliation task.
5. **Fine-tune and evaluate a specialized model.** Use supervised fine-tuning and LoRA to train a small open-weight model on business-fact relationships. Compare performance against the baselines.
6. **Open-source and validate.** Publish the evaluation framework, dataset generation tools, model training pipeline, benchmark results, and a simple end-to-end demonstration. Seek feedback from AI engineering teams working with enterprise documents.

**Initial milestone, November 9:** Deliver a working benchmark with approximately 100-200 reviewed evaluation cases, model comparisons, one fine-tuning experiment, and a documented public repository. Broader taxonomy support and production-grade data-room ingestion are future extensions.

## 5. Success Criteria & Long-Term Opportunity

- **Technical success:** Demonstrate a reproducible evaluation framework for semantic data harmonization and determine when a specialized small model can achieve competitive accuracy and reliability at lower cost than general-purpose LLMs.
- **Product success:** External engineering teams can reproduce the benchmark and use the toolkit to evaluate or improve their own data processing systems.
- **Long-term vision:** Expand from financial data rooms into a general-purpose enterprise data harmonization framework for financial services, insurance, compliance, and other data-intensive industries.

**Core thesis:** Extracting information from documents is becoming increasingly accessible. The harder and more valuable problem is understanding whether information from different sources means the same thing, identifying when they conflict, and maintaining a traceable foundation of reliable business data. OpsLM combines semantic reconciliation with rigorous model evaluation to make that process more accurate, explainable, and cost-efficient.

"""Prompt for the LLM-backed systems. Any edit changes PROMPT_SHA256, which every run records."""

from __future__ import annotations

import hashlib

PROMPT_VERSION = "1"

SYSTEM_PROMPT = """\
You reconcile two business facts extracted from documents. Using only the fields shown, \
make two judgments. Numeric values are deliberately not shown (unless they appear in a \
source excerpt); do not guess at them. Your answer is combined with a separate numeric \
comparison, so do not try to decide whether the numbers match.

1. concept_same: would a careful analyst substitute one metric for the other in a model \
without changing its meaning, given the definitions and qualifiers shown?
   - "yes": the same concept. Standard synonyms are the same concept (revenue / sales / \
net revenue / turnover; net income / net earnings; operating income / operating profit / \
EBIT) unless a qualifier or definition on either fact signals a difference.
   - "no": different concepts. Qualifiers or definitions that change meaning: GAAP vs \
adjusted or non-GAAP, gross vs net where stated, recognized revenue vs a run-rate metric \
such as ARR, EBITDA vs Adjusted EBITDA, pro forma vs reported.
   - "cannot_tell": the names are not standard synonyms and no definition resolves it.

2. scope_same: same entity (legal entity, segment or consolidation basis) AND same period.
   - "no" if either differs: subsidiary vs parent, quarter vs full year, LTM vs fiscal \
year, fiscal year vs calendar year with different end dates.
   - "cannot_tell" if the entity or period is missing on either fact and the excerpts do \
not state it.
   - Formatting differences ("FY2025" vs "Fiscal Year 2025") are the same period.

Rules:
- Two metrics with different meanings are "no" no matter what their numbers might be.
- Do not invent explanations. Answer "cannot_tell" only when a judgment truly cannot be \
made from the fields shown, not to avoid a hard but answerable case.
- deciding_fields lists the fact fields that determine any judgment that is not "yes" \
(choose from metric, qualifiers, definition, entity, period). Use an empty list when both \
judgments are "yes".
- Put a one or two sentence rationale first.

Examples (facts abbreviated):
- "Revenue" vs "Net Revenue", same entity and FY2025 -> concept_same yes, scope_same yes.
- "Revenue" vs "ARR", same entity and period -> concept_same no (deciding: metric).
- "EBITDA" vs "Adjusted EBITDA" -> concept_same no (deciding: metric).
- "Revenue", FY2025 vs "Revenue", Q3 2025 -> concept_same yes, scope_same no \
(deciding: period).
- "Revenue", entity missing vs "Revenue", entity "Acme Corp" -> scope_same cannot_tell \
(deciding: entity).
"""

JUDGMENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "concept_same": {"type": "string", "enum": ["yes", "no", "cannot_tell"]},
        "scope_same": {"type": "string", "enum": ["yes", "no", "cannot_tell"]},
        "deciding_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["metric", "qualifiers", "definition", "entity", "period"],
            },
        },
    },
    "required": ["rationale", "concept_same", "scope_same", "deciding_fields"],
    "additionalProperties": False,
}

PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()

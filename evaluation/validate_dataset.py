"""Sanity-check evaluation/golden_dataset.json before running the evaluation.
 
Run from the repo root:
    python evaluation/validate_dataset.py
    python evaluation/validate_dataset.py --dataset evaluation/golden_dataset.json --root .
 
Checks: valid JSON, required fields, duplicate questions, kb_type values,
kb_type vs. path consistency, and that every expected_source file really exists.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
 
REQUIRED = ("question", "expected_source", "kb_type", "department", "project")
KB_TYPES = {"company", "department", "project"}
 
 
def infer_kb_type(path: str) -> str:
    """Infer the knowledge-base type from an expected source path."""
    # Normalize Windows and Unix paths so the checks work on either platform.
    p = path.replace("\\", "/").lower()

    # Department documents live under the Departments directory.
    if "/departments/" in p:
        return "department"

    # Project paths contain the project directory or project KB name.
    if "/project" in p:
        return "project"

    # Remaining paths are company-wide documents, FAQs, or recurring issues.
    return "company"  # company/, faq/, recurring_problems/
 
 
def main() -> int:
    """Validate the golden dataset and return a process exit status."""
    # Read the dataset path and repository root from the command line.
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evaluation/golden_dataset.json")
    ap.add_argument("--root", default=".", help="repo root that expected_source paths are relative to")
    args = ap.parse_args()
 
    # Loading errors stop validation because there is no dataset to inspect.
    try:
        data = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[FATAL] cannot load {args.dataset}: {e}")
        return 1
 
    errors, warnings = [], []
    root = Path(args.root)
 
    # Check every question's required fields, source file, and KB classification.
    for i, item in enumerate(data, start=1):
        tag = f"#{i}"
        missing = [k for k in REQUIRED if k not in item or item[k] in ("", None)]
        if missing:
            # Skip further checks for incomplete records to avoid misleading errors.
            errors.append(f"{tag} missing fields: {missing}")
            continue
        if item["kb_type"] not in KB_TYPES:
            errors.append(f"{tag} invalid kb_type '{item['kb_type']}'")
        src = item["expected_source"]
        if not (root / src).is_file():
            errors.append(f"{tag} expected_source not found on disk: {src}")
        inferred = infer_kb_type(src)
        if item["kb_type"] != inferred:
            warnings.append(f"{tag} kb_type='{item['kb_type']}' but path looks like '{inferred}': {src}")
 
    # Normalize questions before counting so case and surrounding spaces do not
    # hide duplicate questions.
    qs = [x.get("question", "").strip().lower() for x in data]
    for q, n in Counter(qs).items():
        if n > 1:
            errors.append(f"duplicate question ({n}x): {q[:80]}")
 
            # Flag generic wording that may make retrieval misses ambiguous.
    generic = [x["question"] for x in data if "additional support or resources" in x.get("question", "").lower()]
    if generic:
        warnings.append(
            f"{len(generic)} questions use the generic 'additional support or resources' wording; "
            "many docs contain similar text, so misses on these may not be real retrieval failures"
        )
 
    # Warn when the dataset does not exercise the Project KB at all.
    with_project = sum(1 for x in data if str(x.get("project", "none")).lower() != "none")
    if with_project == 0:
        warnings.append("no question targets a Project KB (project is 'none' everywhere)")
 
    # Print a compact validation report for humans and CI logs.
    print(f"Questions: {len(data)}")
    print("kb_type  :", dict(Counter(x.get("kb_type") for x in data)))
    print("per file :", dict(Counter(x.get("expected_source") for x in data)) if len(data) < 15 else
          f"{len(set(x.get('expected_source') for x in data))} distinct files")
    print(f"\nERRORS ({len(errors)})")
    for e in errors:
        print("  -", e)
    print(f"\nWARNINGS ({len(warnings)})")
    for w in warnings:
        print("  -", w)
    # A nonzero status lets scripts or CI fail when validation finds errors.
    return 1 if errors else 0
 
 
if __name__ == "__main__":
    sys.exit(main())
 
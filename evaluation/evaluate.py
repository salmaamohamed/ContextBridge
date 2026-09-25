"""Retrieval evaluation: Hit Rate@1/3/5 and MRR@5 against the golden dataset.
 
Run from the repo root:
    python evaluation/evaluate.py --search mock                       # test the metrics, no retriever needed
    python evaluation/evaluate.py --search backend.app.retrieval:search   # real retriever (module:function)
 
The retriever must look like:  search(query, top_k, department, project) -> list of results.
Each result needs a source path (dict key 'source' / 'source_path' / 'file_path' / 'path',
optionally nested under 'metadata' or 'payload'; or an attribute with the same name).
 
Outputs (in --out-dir): results.json and failed_cases.md
"""
import argparse
import importlib
import json
from collections import defaultdict
from pathlib import Path
 
KS = (1, 3, 5)
SOURCE_KEYS = ("source", "source_path", "file_path", "path")
 
 
# ---------- helpers  ----------
# that path of all same stracture 
def norm(p) -> str:
    p = str(p).replace("\\", "/").lower()
    return p[2:] if p.startswith("./") else p
 
 #the path of agent that the same path of json i create or not 
def is_match(got: str, expected: list) -> bool:
    g = norm(got)
    for e in map(norm, expected):
        if g == e or g.endswith("/" + e) or e.endswith("/" + g):
            return True
    return False

 
def extract_source(result) -> str:
    """Return a result's source path, wherever the retriever stored it.

    Results may be dictionaries or objects. The source path can be stored
    directly on the result or inside its ``metadata``/``payload`` field.
    """
    def look(obj):
        # Try each accepted source key on the current dictionary or object.
        for k in SOURCE_KEYS:
            v = obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)
            if v:
                return v
        return None
 
    # Prefer a source path stored directly on the result.
    found = look(result)
    if found:
        return str(found)

    # Some retrievers wrap the source path in metadata or payload.
    for nested in ("metadata", "payload"):
        sub = result.get(nested) if isinstance(result, dict) else getattr(result, nested, None)
        if sub:
            found = look(sub)
            if found:
                return str(found)

    # No supported source field was present.
    return ""
 
 
# ---------- metrics ----------
def first_rank(sources: list, expected: list, max_k: int = 5):
    """Return the 1-based rank of the first matching source.

    Only the first ``max_k`` results are checked. Return ``None`` when no
    expected source appears within that cutoff.
    """
    # enumerate starts at 1 because search-result ranks are 1-based.
    for i, s in enumerate(sources[:max_k], start=1):
        if is_match(s, expected):
            return i
    return None
 
 
def hit_at_k(rank, k: int) -> int:
    """
    Returns 1 (a hit) if the correct expected source appears within the top K retrieved results, otherwise 0.
    For example, hit_at_3 returns 1 if the correct answer is ranked 1st, 2nd, or 3rd.
    """
    return int(rank is not None and rank <= k)
 
 
def reciprocal_rank(rank, k: int = 5) -> float:
    """
    Calculates the Reciprocal Rank used for the MRR (Mean Reciprocal Rank) metric.
    If the correct expected source is at the 1st position, it scores 1 (1/1 = 1.0).
    If it is at the 2nd position, it scores 0.5 (1/2 = 0.5), and so forth.
    The further down the correct result appears, the lower its score.
    """
    return 1.0 / rank if rank is not None and rank <= k else 0.0
 
 
# ---------- retrievers ----------
#  task omnia 
def load_search(spec: str, dataset: list):
    if spec == "mock":
        return make_mock(dataset)
    module_name, func_name = spec.split(":")
    return getattr(importlib.import_module(module_name), func_name)
 
 
def make_mock(dataset: list):
    """Fake retriever with a KNOWN result pattern, used to verify the metric math.
    item i%4==0 -> correct at rank 1, 1 -> rank 3, 2 -> rank 5, 3 -> miss.
    Expected on a balanced set: Hit@1=.25, Hit@3=.50, Hit@5=.75, MRR@5=(1+1/3+1/5+0)/4=.383"""
    table = {}
    for i, item in enumerate(dataset):
        table[item["question"]] = (item["expected_source"], i % 4)
 
    def mock_search(query, top_k=5, department=None, project=None):
        expected, mode = table[query]
        results = [{"source": f"dummy/other_{n}.txt", "score": 0.5} for n in range(top_k)]
        pos = {0: 0, 1: 2, 2: 4}.get(mode)
        if pos is not None and pos < top_k:
            results[pos] = {"source": expected, "score": 0.9}
        return results
 
    return mock_search
 
 
# ---------- main ----------
def main():
    """Run retrieval evaluation for every question in the golden dataset."""
    # Define the command-line options that control the evaluation run.
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evaluation/golden_dataset.json")
    ap.add_argument("--search", required=True, help="'mock' or 'module.path:function'")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--no-filters", action="store_true", help="ignore department/project filters")
    ap.add_argument("--dedupe", action="store_true", help="collapse chunks from the same file (document-level ranking)")
    ap.add_argument("--out-dir", default="evaluation")
    args = ap.parse_args()
 
    # Load the expected answers and choose either the mock or real retriever.
    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    search = load_search(args.search, dataset)
    rows = []
 
    # Evaluate each question independently so its rank and metric values can
    # later be summarized overall and by knowledge-base type.
    for i, item in enumerate(dataset, start=1):
        # "all" and "none" mean that no department/project filter is needed.
        dept = None if args.no_filters or str(item["department"]).lower() == "all" else item["department"]
        proj = None if args.no_filters or str(item["project"]).lower() == "none" else item["project"]

        # Ask the retriever for ranked results and keep only their source paths.
        results = search(query=item["question"], top_k=args.top_k, department=dept, project=proj)
        sources = [extract_source(r) for r in results]

        # Optionally count each source file once instead of counting chunks.
        if args.dedupe:
            seen, uniq = set(), []
            for s in sources:
                if norm(s) not in seen:
                    seen.add(norm(s))
                    uniq.append(s)
            sources = uniq

        # Support datasets with one expected source or several alternatives.
        expected = item["expected_sources"] if "expected_sources" in item else [item["expected_source"]]
        rank = first_rank(sources, expected, max(KS))

        # Store everything needed for metric summaries and failure reports.
        rows.append({
            "id": item.get("id", f"q{i:03d}"), "question": item["question"], "kb_type": item["kb_type"],
            "expected": expected, "retrieved": sources[:max(KS)], "rank": rank,
            "filters": {"department": dept, "project": proj},
            **{f"hit@{k}": hit_at_k(rank, k) for k in KS}, "rr": reciprocal_rank(rank, 5),
        })
 
    def summarize(subset):
        """Calculate average retrieval metrics for a group of evaluation rows."""
        n = len(subset)
        # Averaging 0/1 hit values produces the hit rate for each cutoff.
        out = {f"Hit@{k}": sum(r[f"hit@{k}"] for r in subset) / n for k in KS}
        # Average reciprocal ranks to get Mean Reciprocal Rank at 5.
        out["MRR@5"] = sum(r["rr"] for r in subset) / n
        out["n"] = n
        return out
 
    # Calculate one overall summary and separate summaries for each KB type.
    overall = summarize(rows)
    by_kb = defaultdict(list)
    for r in rows:
        by_kb[r["kb_type"]].append(r)
 
    # Print the summaries as a fixed-width table for quick terminal inspection.
    print(f"\n{'group':<12}{'n':>5}{'Hit@1':>8}{'Hit@3':>8}{'Hit@5':>8}{'MRR@5':>8}")
    for name, subset in [("OVERALL", rows)] + sorted(by_kb.items()):
        s = summarize(subset)
        print(f"{name:<12}{s['n']:>5}{s['Hit@1']:>8.3f}{s['Hit@3']:>8.3f}{s['Hit@5']:>8.3f}{s['MRR@5']:>8.3f}")
 
    # Save machine-readable summaries and per-question results as JSON.
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps({"overall": overall, "by_kb_type": {k: summarize(v) for k, v in by_kb.items()}, "rows": rows},
                   indent=2, ensure_ascii=False), encoding="utf-8")
 
    # Build a Markdown report for questions with no correct result in the top K.
    failed = [r for r in rows if r["rank"] is None]
    lines = [f"# Failed cases ({len(failed)} of {len(rows)} missed the top-{max(KS)})\n",
             "| ID | KB | Question | Expected | Retrieved (top 5) | Filters |", "|---|---|---|---|---|---|"]
    for r in failed:
        lines.append(f"| {r['id']} | {r['kb_type']} | {r['question']} | {', '.join(r['expected'])} | "
                     f"{'<br>'.join(r['retrieved']) or '(nothing)'} | {r['filters']} |")
    # Also report correct results that were retrieved, but not at rank 1.
    late = [r for r in rows if r["rank"] and r["rank"] > 1]
    lines += [f"\n## Found but not at rank 1 ({len(late)})\n", "| ID | Rank | Question | Expected |", "|---|---|---|---|"]
    for r in late:
        lines.append(f"| {r['id']} | {r['rank']} | {r['question']} | {', '.join(r['expected'])} |")
    (out_dir / "failed_cases.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {out_dir/'results.json'} and {out_dir/'failed_cases.md'}")
 
 
if __name__ == "__main__":
    main()
 
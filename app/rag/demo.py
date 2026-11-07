"""Synthetic, authored fixture. Not real paper excerpts or live AI output."""
import json

DEMO_CHUNKS = [
    {"source_file": "demo_attention_notes.pdf", "page_number": 1, "page_base": 1, "kind": "text",
     "text": "In this synthetic example, dense attention compares every token with every other token. The attention score matrix grows quadratically with sequence length.", "image_paths": [], "score": 0.91},
    {"source_file": "demo_sparse_notes.pdf", "page_number": 2, "page_base": 1, "kind": "text",
     "text": "In this synthetic example, a fixed sparse attention pattern reduces the number of token pairs. The pattern can omit long-range dependencies needed by some tasks.", "image_paths": [], "score": 0.86},
    {"source_file": "demo_evaluation_notes.pdf", "page_number": 3, "page_base": 1, "kind": "text",
     "text": "In this synthetic example, no matched hardware latency measurements are available. A reduction in theoretical operations alone does not establish a wall-clock speedup.", "image_paths": [], "score": 0.78},
]


def demo_generate(prompt, sources, include_images=True):
    labels = {"demo_attention_notes.pdf": "Dense attention has quadratic score-matrix growth in this example.",
        "demo_sparse_notes.pdf": "Sparse attention can omit task-relevant long-range dependencies in this example.",
        "demo_evaluation_notes.pdf": "These notes do not establish a measured latency improvement."}
    claims = [{"text": labels[s["document"]], "relation": "limitation" if "evaluation" in s["document"] else "finding",
        "evidence": [{"source_id": s["id"], "quote": s["text"]}]} for s in sources]
    return json.dumps({"claims": claims, "gaps": ["Matched hardware latency and quality measurements are missing."],
        "experiments": [{"hypothesis": "A sparse pattern lowers latency while preserving task quality.",
        "intervention": "Compare dense and sparse attention at equal model size and sequence length on the same device.",
        "measurement": "Record median latency, peak memory, and task score across repeated runs and random seeds.",
        "falsifier": "No repeatable latency reduction, or task quality falls beyond a predefined tolerance."}]}), {
        "provider": "synthetic_fixture", "model": "none — scripted demonstration", "images_seen": 0, "failed_attempts": []}

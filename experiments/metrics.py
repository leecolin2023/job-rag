"""Job-level ranking metrics with explicit incomplete-judgment semantics."""
import math
import random
import statistics


def ranking_metrics(ranking, grades, ks=(1, 3, 5, 10, 20, 50), judgment_scope="seed"):
    ranking = list(dict.fromkeys(ranking))
    positives = {key for key, grade in grades.items() if grade > 0}
    prefix = "" if judgment_scope == "exhaustive" else ("pooled_" if judgment_scope == "pooled" else "seed_")
    output = {}
    for k in ks:
        selected = ranking[:k]
        hits = sum(key in positives for key in selected)
        output[f"{prefix}recall@{k}"] = hits / len(positives) if positives else None
        output[f"{prefix}hit_rate@{k}"] = float(hits > 0) if positives else None
        output[f"judged_fraction@{k}"] = sum(key in grades for key in selected) / len(selected) if selected else 0.0
        if judgment_scope == "exhaustive":
            output[f"precision@{k}"] = hits / k
        else:
            output[f"precision_lower_bound@{k}"] = hits / k
        gains = [(2 ** grades.get(key, 0) - 1) / math.log2(i + 2) for i, key in enumerate(selected)]
        ideal = sorted(grades.values(), reverse=True)[:k]
        idcg = sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(ideal))
        output[f"{prefix}ndcg@{k}"] = sum(gains) / idcg if idcg else None
    output[f"{prefix}mrr"] = next((1 / (i + 1) for i, key in enumerate(ranking) if key in positives), 0.0) if positives else None
    return output


def mean_metrics(items):
    keys = {key for item in items for key in item}
    return {key: statistics.mean([item[key] for item in items if item.get(key) is not None])
            for key in sorted(keys) if any(item.get(key) is not None for item in items)}


def paired_bootstrap(a, b, repeats=2000, seed=20261025, groups=None):
    """Paired cluster bootstrap; paraphrases are not independent experimental units."""
    groups = groups if groups is not None else list(range(len(a)))
    pairs = [(x, y, group) for x, y, group in zip(a, b, groups) if x is not None and y is not None]
    if not pairs:
        return None
    rng = random.Random(seed)
    deltas = [y - x for x, y, _ in pairs]
    clusters = {}
    for x, y, group in pairs:
        clusters.setdefault(group, []).append(y - x)
    keys = list(clusters)
    samples = sorted(statistics.mean([delta for key in rng.choices(keys, k=len(keys)) for delta in clusters[key]]) for _ in range(repeats))
    return {"mean_delta": statistics.mean(deltas), "ci95": [samples[int(.025 * repeats)], samples[min(int(.975 * repeats), repeats - 1)]],
            "paired_queries": len(pairs), "clusters": len(clusters), "unit": "query_group", "seed": seed}

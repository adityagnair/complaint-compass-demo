import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from backend.ai.clustering import cluster_embeddings
from backend.ai.embeddings import EMBEDDING_DIMENSIONS, MODEL_NAME, embed_texts
from backend.ai.labeling import label_clusters
from backend.ai.preprocessing import normalize_complaint
from backend.database import database
from backend.services.prioritization import (
    RELATIVE_NORMALIZATION,
    SCORING_FORMULA,
    SCORING_WEIGHTS,
    SEVERITY_NORMALIZATION,
    score_issues,
)


def _to_datetime(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _find_duplicates(records: list[dict], embeddings: np.ndarray, threshold: float, window_days: int) -> dict[int, int]:
    customers: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        customer_id = record.get("customer_id")
        if customer_id:
            customers[str(customer_id)].append(index)

    duplicates: dict[int, int] = {}
    for indices in customers.values():
        indices.sort(key=lambda index: (_to_datetime(records[index]["submitted_at"]), index))
        primaries: list[int] = []
        for index in indices:
            current_date = _to_datetime(records[index]["submitted_at"])
            candidates = [
                previous for previous in primaries
                if abs((current_date - _to_datetime(records[previous]["submitted_at"])).total_seconds()) <= window_days * 86400
            ]
            if candidates:
                similarities = embeddings[candidates] @ embeddings[index]
                best_offset = int(np.argmax(similarities))
                if float(similarities[best_offset]) >= threshold:
                    duplicates[index] = candidates[best_offset]
                    continue
            primaries.append(index)
    return duplicates


def _representative(indices: list[int], embeddings: np.ndarray, records: list[dict]) -> str:
    vectors = embeddings[indices]
    center = vectors.mean(axis=0)
    norm = np.linalg.norm(center)
    if norm:
        center = center / norm
    best = int(np.argmax(vectors @ center))
    return records[indices[best]]["complaint_text"]


def run_analysis(*, min_cluster_size: int = 2, duplicate_similarity_threshold: float = 0.92, duplicate_window_days: int = 30) -> dict:
    with database() as connection:
        records = [dict(row) for row in connection.execute(
            """SELECT complaint_id, customer_id, complaint_text, submitted_at, severity,
                      normalized_text, embedding, embedding_model
               FROM complaints ORDER BY submitted_at ASC, id ASC"""
        ).fetchall()]

    if not records:
        raise ValueError("Upload or add complaints before running analysis")

    normalized = [normalize_complaint(record["complaint_text"]) for record in records]
    if any(not value for value in normalized):
        raise ValueError("At least one complaint has no usable text after preprocessing")
    vectors: list[np.ndarray | None] = [None] * len(records)
    missing_indexes = []
    for index, record in enumerate(records):
        if record.get("normalized_text") == normalized[index] and record.get("embedding_model") == MODEL_NAME and record.get("embedding"):
            try:
                cached = np.asarray(json.loads(record["embedding"]), dtype=np.float32)
                if cached.ndim == 1 and cached.size == EMBEDDING_DIMENSIONS:
                    vectors[index] = cached
                    continue
            except (ValueError, TypeError):
                pass
        missing_indexes.append(index)
    if missing_indexes:
        encoded = embed_texts([normalized[index] for index in missing_indexes])
        for index, vector in zip(missing_indexes, encoded, strict=True):
            vectors[index] = vector
    embeddings = np.stack(vectors)
    duplicates = _find_duplicates(records, embeddings, duplicate_similarity_threshold, duplicate_window_days)
    primary_indices = [index for index in range(len(records)) if index not in duplicates]
    model_labels = cluster_embeddings(embeddings[primary_indices], min_cluster_size)

    primary_cluster: dict[int, int] = {
        original_index: int(model_label)
        for original_index, model_label in zip(primary_indices, model_labels, strict=True)
    }
    for duplicate_index, primary_index in duplicates.items():
        primary_cluster[duplicate_index] = primary_cluster.get(primary_index, -1)

    groups: dict[int, list[int]] = defaultdict(list)
    for index, cluster_number in primary_cluster.items():
        if cluster_number >= 0 and index not in duplicates:
            groups[cluster_number].append(index)
    # Link repeat submissions into their primary report's issue cluster.
    for duplicate_index, primary_index in duplicates.items():
        cluster_number = primary_cluster.get(primary_index, -1)
        if cluster_number >= 0:
            groups[cluster_number].append(duplicate_index)

    run_id = uuid.uuid4().hex
    cluster_ids = {cluster_number: f"{run_id[:10]}-{cluster_number + 1}" for cluster_number in groups}
    label_inputs = [
        {"label_id": cluster_number, "texts": [records[index]["complaint_text"] for index in groups[cluster_number]]}
        for cluster_number in sorted(groups)
    ]
    labels, label_model = label_clusters(label_inputs)

    clusters = []
    for cluster_number, indices in sorted(groups.items()):
        primary_members = [index for index in indices if index not in duplicates]
        customer_ids = {records[index].get("customer_id") for index in primary_members if records[index].get("customer_id")}
        duplicate_count = sum(index in duplicates for index in indices)
        cluster_id = cluster_ids[cluster_number]
        label, label_source = labels[cluster_number]
        clusters.append({
            "cluster_id": cluster_id,
            "label": label,
            "label_source": label_source,
            "representative_text": _representative(primary_members, embeddings, records),
            "complaint_count": len(primary_members),
            "submission_count": len(indices),
            "affected_customers": len(customer_ids),
            "duplicate_count": duplicate_count,
            "average_severity": round(float(np.mean([records[index]["severity"] for index in primary_members])), 2),
            "members": indices,
        })
    score_issues(clusters)

    with database() as connection:
        connection.execute(
            """INSERT INTO analysis_runs (run_id, embedding_model, clustering_method, min_cluster_size,
                 duplicate_similarity_threshold, duplicate_window_days, complaints_processed, issues_found, label_model,
                 scoring_formula, scoring_weights, severity_normalization, relative_normalization)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, MODEL_NAME, "scikit-learn HDBSCAN / euclidean; cosine-neighbor recovery for all-noise runs", min_cluster_size,
             duplicate_similarity_threshold, duplicate_window_days, len(records), len(clusters), label_model,
             SCORING_FORMULA, json.dumps(SCORING_WEIGHTS, sort_keys=True), SEVERITY_NORMALIZATION, RELATIVE_NORMALIZATION),
        )
        for cluster in clusters:
            connection.execute(
                """INSERT INTO issue_clusters (cluster_id, run_id, label, label_source, representative_text,
                     complaint_count, submission_count, affected_customers, duplicate_count, average_severity,
                     severity_score, frequency_score, impact_score, priority_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cluster["cluster_id"], run_id, cluster["label"], cluster["label_source"], cluster["representative_text"],
                 cluster["complaint_count"], cluster["submission_count"], cluster["affected_customers"],
                 cluster["duplicate_count"], cluster["average_severity"], cluster["severity_score"],
                 cluster["frequency_score"], cluster["impact_score"], cluster["priority_score"]),
            )
        for index, record in enumerate(records):
            cluster_number = primary_cluster.get(index, -1)
            cluster_id = cluster_ids.get(cluster_number)
            duplicate_index = duplicates.get(index)
            connection.execute(
                """UPDATE complaints SET normalized_text = ?, embedding = ?, embedding_model = ?, issue_cluster_id = ?, duplicate_of = ?
                   WHERE complaint_id = ?""",
                (normalized[index], json.dumps(embeddings[index].tolist(), separators=(",", ":")), MODEL_NAME, cluster_id,
                 records[duplicate_index]["complaint_id"] if duplicate_index is not None else None, record["complaint_id"]),
            )

    return {
        "run_id": run_id,
        "embedding_model": MODEL_NAME,
        "clustering_method": "scikit-learn HDBSCAN with cosine-neighbor recovery for all-noise runs",
        "complaints_processed": len(records),
        "issues_found": len(clusters),
        "unclustered_count": sum(primary_cluster.get(index, -1) < 0 and index not in duplicates for index in range(len(records))),
        "duplicate_submissions": len(duplicates),
        "label_model": label_model,
        "scoring_formula": SCORING_FORMULA,
        "scoring_weights": SCORING_WEIGHTS,
        "severity_normalization": SEVERITY_NORMALIZATION,
        "relative_normalization": RELATIVE_NORMALIZATION,
        "clusters": [
            {key: value for key, value in cluster.items() if key != "members"}
            for cluster in sorted(clusters, key=lambda item: (-item["priority_score"], item["label"]))
        ],
    }

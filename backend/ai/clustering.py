import numpy as np


def cluster_embeddings(embeddings: np.ndarray, min_cluster_size: int = 2) -> np.ndarray:
    if len(embeddings) < min_cluster_size:
        return np.full(len(embeddings), -1, dtype=int)

    from sklearn.cluster import HDBSCAN

    clusterer = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        metric="euclidean",
        cluster_selection_method="eom",
        allow_single_cluster=False,
        n_jobs=1,
    )
    labels = clusterer.fit_predict(embeddings)
    if np.any(labels >= 0):
        return labels

    # HDBSCAN can mark every point as noise on a tiny seed dataset. Preserve
    # obvious semantic pairs in that case so the first-run demo is useful.
    vectors = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.maximum(norms, 1e-12)
    similarities = normalized @ normalized.T
    parents = list(range(len(vectors)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for left in range(len(vectors)):
        for right in range(left + 1, len(vectors)):
            if similarities[left, right] >= 0.6:
                left_root, right_root = find(left), find(right)
                if left_root != right_root:
                    parents[right_root] = left_root

    groups: dict[int, list[int]] = {}
    for index in range(len(vectors)):
        groups.setdefault(find(index), []).append(index)
    fallback_labels = np.full(len(vectors), -1, dtype=int)
    next_label = 0
    for members in groups.values():
        if len(members) >= min_cluster_size:
            fallback_labels[members] = next_label
            next_label += 1
    return fallback_labels

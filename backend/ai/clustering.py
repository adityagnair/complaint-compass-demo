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

    # HDBSCAN can mark every point as noise on a tiny seed dataset. Recover
    # tight semantic groups, while preventing single-link chains from joining
    # complaints that are only connected through one borderline example.
    vectors = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.maximum(norms, 1e-12)
    similarities = normalized @ normalized.T
    threshold = 0.6
    neighbor_counts = (similarities >= threshold).sum(axis=1)
    order = sorted(range(len(vectors)), key=lambda index: (-int(neighbor_counts[index]), index))
    groups: list[list[int]] = []
    for index in order:
        compatible = []
        for group_index, members in enumerate(groups):
            cross_similarities = similarities[index, members]
            if np.all(cross_similarities >= threshold):
                compatible.append((float(np.mean(cross_similarities)), group_index))
        if compatible:
            _, group_index = max(compatible, key=lambda item: (item[0], -item[1]))
            groups[group_index].append(index)
        else:
            groups.append([index])
    fallback_labels = np.full(len(vectors), -1, dtype=int)
    next_label = 0
    for members in groups:
        if len(members) >= min_cluster_size:
            fallback_labels[members] = next_label
            next_label += 1
    return fallback_labels

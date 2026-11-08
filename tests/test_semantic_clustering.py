import numpy as np
import pytest

from backend.ai.clustering import cluster_embeddings
from backend.ai.embeddings import EmbeddingModelUnavailable, embed_texts


@pytest.mark.integration
def test_manual_labeled_examples_keep_issue_families_semantically_close():
    examples = [
        ("payment", "My card was charged twice for a single purchase."),
        ("payment", "I was billed two times for the same order."),
        ("payment", "The transaction deducted money from my account twice."),
        ("payment", "I see a duplicate charge on my bank statement."),
        ("delivery", "My package arrived several days later than promised."),
        ("delivery", "The shipment is delayed and has not arrived yet."),
        ("delivery", "Delivery is late compared with the expected date."),
        ("delivery", "My order is taking too long to reach me."),
        ("refund", "I am still waiting for money from my returned item."),
        ("refund", "The refund has not appeared in my account."),
        ("refund", "My reimbursement for the cancelled order is overdue."),
        ("refund", "I have not received the money promised after returning this."),
    ]
    try:
        vectors = embed_texts([text for _, text in examples])
    except EmbeddingModelUnavailable as error:
        pytest.skip(str(error))

    labels = [label for label, _ in examples]
    similarities = vectors @ vectors.T
    np.fill_diagonal(similarities, -1)
    nearest = similarities.argmax(axis=1)
    accuracy = sum(labels[index] == labels[nearest[index]] for index in range(len(labels))) / len(labels)
    assert accuracy >= 0.83, f"Nearest-neighbor issue family accuracy was {accuracy:.0%}"

    clusters = cluster_embeddings(vectors, min_cluster_size=2)
    cluster_purities = []
    for cluster_id in set(clusters) - {-1}:
        members = [index for index, value in enumerate(clusters) if value == cluster_id]
        purity = max(sum(labels[index] == label for index in members) for label in set(labels)) / len(members)
        cluster_purities.append(purity)
    assert cluster_purities, "HDBSCAN should find at least one group in the labeled examples"
    assert sum(cluster_purities) / len(cluster_purities) >= 0.75

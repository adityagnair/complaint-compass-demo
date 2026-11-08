import json
import os
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from sklearn.feature_extraction.text import TfidfVectorizer

PAYMENT = {"payment", "pay", "paid", "charge", "charged", "debit", "debited", "deducted", "money", "transaction", "billing", "bill"}
DUPLICATE = {"twice", "two", "double", "duplicate", "again", "multiple", "extra"}


def _fallback_label(texts: list[str]) -> str:
    combined = " ".join(text.casefold() for text in texts)
    words = set(re.findall(r"[a-z]+", combined))
    if words & PAYMENT and words & DUPLICATE:
        return "Duplicate payments"
    if words & {"refund", "refunded", "reimbursement"}:
        return "Refund issues"
    if words & {"delivery", "delivered", "shipment", "shipping", "package"}:
        return "Delivery issues"
    if words & {"login", "password", "sign", "account", "access"}:
        return "Account access issues"
    if words & {"cancel", "cancelled", "canceled", "subscription"}:
        return "Cancellation issues"

    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=100)
        matrix = vectorizer.fit_transform(texts)
        scores = matrix.mean(axis=0).A1
        terms = vectorizer.get_feature_names_out()
        selected = [terms[index] for index in scores.argsort()[::-1] if terms[index] not in {"issue", "problem", "complaint"}][:3]
        if selected:
            return " ".join(word.title() for word in selected)
    except ValueError:
        pass
    return "Related customer reports"


def _clean_label(value: str) -> str | None:
    label = re.sub(r"[\r\n]+", " ", value or "").strip().strip("\"'` .:-")
    label = " ".join(label.split())
    if not label or len(label) > 60 or len(label.split()) > 7:
        return None
    if label.casefold() in {"issue", "complaint", "customer complaint", "related reports", "various issues"}:
        return None
    return label[:1].upper() + label[1:]


def label_clusters(clusters: list[dict]) -> tuple[dict[int, tuple[str, str]], str | None]:
    fallback = {item["label_id"]: (_fallback_label(item["texts"]), "keywords") for item in clusters}
    if not clusters or os.getenv("OLLAMA_LABELS", "true").lower() not in {"1", "true", "yes", "on"}:
        return fallback, None

    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    examples = [
        {"cluster_id": item["label_id"], "complaints": item["texts"][:8]}
        for item in clusters
    ]
    prompt = (
        "Name each group of customer complaints with a short, factual issue label (2-5 words). "
        "Use only the details in the examples. Return JSON exactly as "
        '{"labels":[{"cluster_id":0,"label":"..."}]}.\n'
        + json.dumps(examples, ensure_ascii=False)
    )
    payload = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}}).encode("utf-8")
    request = Request(f"{base_url}/api/generate", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))) as response:
            answer = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(answer.get("response", "{}"))
        proposed = {int(item["cluster_id"]): _clean_label(item.get("label", "")) for item in parsed.get("labels", [])}
        resolved = {
            item["label_id"]: (proposed[item["label_id"]], "ollama")
            if proposed.get(item["label_id"])
            else fallback[item["label_id"]]
            for item in clusters
        }
        return resolved, model
    except (OSError, URLError, TimeoutError, ValueError, KeyError, TypeError):
        return fallback, None

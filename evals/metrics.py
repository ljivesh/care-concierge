"""Precision, recall and a confusion matrix, printed as plain text."""

from collections import Counter


def per_class(pairs: list[tuple[str, str]], classes: list[str]) -> list[dict]:
    """pairs = (expected, predicted). Precision: of the rows we called X, how many were X.
    Recall: of the rows that were X, how many we called X."""
    rows = []
    for label in classes:
        true_positive = sum(1 for expected, predicted in pairs if expected == label and predicted == label)
        predicted_as = sum(1 for _, predicted in pairs if predicted == label)
        actually = sum(1 for expected, _ in pairs if expected == label)
        rows.append(
            {
                "class": label,
                "precision": true_positive / predicted_as if predicted_as else None,
                "recall": true_positive / actually if actually else None,
                "support": actually,
            }
        )
    return rows


def _ratio(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.2f}"


def print_per_class(title: str, pairs: list[tuple[str, str]], classes: list[str]) -> None:
    print(f"\n{title}")
    print(f"  {'class':16} precision  recall  rows")
    for row in per_class(pairs, classes):
        if row["support"] == 0 and row["precision"] is None:
            continue  # a class with no rows and no predictions has nothing to report
        print(f"  {row['class']:16} {_ratio(row['precision'])}      {_ratio(row['recall'])}   {row['support']:>3}")


def print_confusion(title: str, pairs: list[tuple[str, str]], classes: list[str]) -> None:
    """Rows are the expected label, columns the predicted one. Empty columns are dropped."""
    counts = Counter(pairs)
    predicted = [c for c in classes if any(p == c for _, p in pairs)]
    predicted += sorted({p for _, p in pairs} - set(classes))  # e.g. FAILED
    expected = [c for c in classes if any(e == c for e, _ in pairs)]
    short = {c: c[:9] for c in predicted}
    print(f"\n{title}  (rows: expected, columns: predicted)")
    print("  " + " " * 16 + " ".join(f"{short[c]:>9}" for c in predicted))
    for e in expected:
        print(f"  {e:16}" + " ".join(f"{counts[(e, p)] or '.':>9}" for p in predicted))


def accuracy(pairs: list[tuple[str, str]]) -> float:
    return sum(1 for expected, predicted in pairs if expected == predicted) / len(pairs) if pairs else 0.0

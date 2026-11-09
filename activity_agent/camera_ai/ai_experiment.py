from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "qa_samples.csv"
REQUIRED_COLUMNS = {"actual_present", "predicted_present", "confidence"}


def main():
    if not DATA_FILE.is_file():
        raise SystemExit(f"QA dataset not found: {DATA_FILE}")

    data = pd.read_csv(DATA_FILE)
    missing = REQUIRED_COLUMNS.difference(data.columns)
    if missing:
        raise SystemExit(f"QA dataset is missing columns: {', '.join(sorted(missing))}")

    data = data.dropna(subset=list(REQUIRED_COLUMNS))
    if not set(data["actual_present"].unique()).issubset({0, 1}):
        raise SystemExit("actual_present values must be 0 or 1")
    if not set(data["predicted_present"].unique()).issubset({0, 1}):
        raise SystemExit("predicted_present values must be 0 or 1")

    features = data[["predicted_present", "confidence"]]
    target = data["actual_present"].astype(int)

    print("Dataset size:", len(data))
    print("Class distribution:")
    print(target.value_counts())

    if len(data) < 20 or target.nunique() < 2 or target.value_counts().min() < 2:
        print("Experiment status: LOW — not enough balanced labelled samples.")
        print("At least 20 labelled rows and both classes are required; model not trained.")
        return

    train_features, test_features, train_target, test_target = train_test_split(
        features,
        target,
        test_size=0.3,
        random_state=42,
        stratify=target,
    )

    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(train_features, train_target)
    predictions = model.predict(test_features)

    print("\n===== RANDOM FOREST RESULTS =====")
    print("Accuracy:", round(accuracy_score(test_target, predictions), 3))
    print("Precision:", round(precision_score(test_target, predictions, zero_division=0), 3))
    print("Recall:", round(recall_score(test_target, predictions, zero_division=0), 3))
    print("F1-score:", round(f1_score(test_target, predictions, zero_division=0), 3))


if __name__ == "__main__":
    main()

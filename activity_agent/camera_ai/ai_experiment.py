import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# Load data
df = pd.read_csv("qa_samples.csv")

# Features and target
X = df[["predicted_present", "confidence"]]
y = df["actual_present"]

# Check dataset
print("Dataset size:", len(df))
print("Class distribution:")
print(y.value_counts())

if len(df) < 20 or y.nunique() < 2:
    print("Not enough data for reliable Random Forest evaluation.")
    print("Collect more labelled samples first.")
else:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight="balanced"
    )

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    print("\n===== RANDOM FOREST RESULTS =====")
    print("Accuracy:", accuracy_score(y_test, predictions))
    print("Precision:", precision_score(y_test, predictions, zero_division=0))
    print("Recall:", recall_score(y_test, predictions, zero_division=0))
    print("F1-score:", f1_score(y_test, predictions, zero_division=0))
"""Reproducible Random Forest experiment with participant-disjoint holdout."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import random

FEATURES = ('active_ratio', 'work_app_ratio', 'presence_ratio', 'task_completion_ratio')
LABELS = ('Low', 'Medium', 'High')
FIELDS = ('participant_id', 'sample_id', 'data_kind', *FEATURES, 'label')


def demo_rows(seed=42):
    """Five fictional participants, 90 windows each; labels are synthetic assumptions."""
    rng = random.Random(seed)
    rows = []
    for participant in range(1, 6):
        for number in range(90):
            latent = rng.uniform(0, 1)
            values = [round(min(1, max(0, latent + rng.gauss(0, 0.20))), 5) for _ in FEATURES]
            label = LABELS[min(2, int(min(0.999, max(0, latent + rng.gauss(0, 0.10))) * 3))]
            rows.append(
                dict(zip(FIELDS, (f'demo-{participant:02}', f'{participant}-{number}', 'synthetic', *values, label)))
            )
    return rows


def validate_rows(rows, data_kind):
    if data_kind not in {'real', 'synthetic'}:
        raise ValueError('data_kind must be real or synthetic.')
    if len(rows) < 30:
        raise ValueError('At least 30 labeled windows are required for this experiment.')
    keys = set()
    for row in rows:
        if set(row) != set(FIELDS):
            raise ValueError(f'CSV must contain exactly {FIELDS}; no raw camera or personal fields.')
        if row['data_kind'] != data_kind:
            raise ValueError('Dataset provenance does not match --data-kind.')
        if not row['participant_id'] or not row['sample_id'] or row['sample_id'] in keys:
            raise ValueError('Participant IDs and globally unique sample IDs are required.')
        keys.add(row['sample_id'])
        if row['label'] not in LABELS:
            raise ValueError('Labels must be Low, Medium or High.')
        for feature in FEATURES:
            value = float(row[feature])
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{feature} must be finite and between 0 and 1.')
    if len({r['participant_id'] for r in rows}) < 5:
        raise ValueError('Use at least 5 participants for participant-disjoint evaluation.')
    if {r['label'] for r in rows} != set(LABELS):
        raise ValueError('All three labels are required.')


def experiment(rows, data_kind='synthetic', seed=42):
    validate_rows(rows, data_kind)
    import sklearn
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from sklearn.model_selection import GroupShuffleSplit

    x = np.array([[float(row[name]) for name in FEATURES] for row in rows])
    y = np.array([row['label'] for row in rows])
    groups = np.array([row['participant_id'] for row in rows])
    train, test = next(GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=seed).split(x, y, groups))
    if set(y[train]) != set(LABELS) or set(y[test]) != set(LABELS):
        raise ValueError('This participant split lacks class coverage. Collect more labeled participants/windows.')
    forest = RandomForestClassifier(
        n_estimators=200, max_depth=6, min_samples_leaf=3, class_weight='balanced', random_state=seed, n_jobs=1
    )
    forest.fit(x[train], y[train])
    predicted = forest.predict(x[test])
    report = classification_report(y[test], predicted, labels=LABELS, output_dict=True, zero_division=0)
    majority = Counter(y[train]).most_common(1)[0][0]
    return {
        'status': 'experimental',
        'data_kind': data_kind,
        'limitation': 'Synthetic demonstration only; not evidence of real employee productivity.'
        if data_kind == 'synthetic'
        else 'Small consented research sample; not validated for employment decisions.',
        'seed': seed,
        'sklearn_version': sklearn.__version__,
        'model': forest.get_params(),
        'features': list(FEATURES),
        'labels': list(LABELS),
        'samples': len(rows),
        'split': {
            'method': 'GroupShuffleSplit by participant',
            'train_samples': len(train),
            'test_samples': len(test),
            'train_participants': len(set(groups[train])),
            'test_participants': len(set(groups[test])),
            'participant_overlap': len(set(groups[train]) & set(groups[test])),
        },
        'accuracy': float(accuracy_score(y[test], predicted)),
        'macro_f1': report['macro avg']['f1-score'],
        'weighted_f1': report['weighted avg']['f1-score'],
        'baseline_accuracy': float(accuracy_score(y[test], [majority] * len(test))),
        'per_class': {name: report[name] for name in LABELS},
        'confusion_matrix': confusion_matrix(y[test], predicted, labels=LABELS).tolist(),
        'feature_importance': dict(zip(FEATURES, forest.feature_importances_.tolist())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, help='Labeled aggregate CSV; omitted uses generated synthetic data.')
    parser.add_argument('--data-kind', choices=('real', 'synthetic'), default='synthetic')
    parser.add_argument('--write-demo', type=Path)
    parser.add_argument('--output', type=Path, default=Path('.runtime/qa/ai-report.json'))
    args = parser.parse_args()
    if args.csv:
        with args.csv.open(newline='', encoding='utf-8') as stream:
            rows = list(csv.DictReader(stream))
        checksum = hashlib.sha256(args.csv.read_bytes()).hexdigest()
    else:
        if args.data_kind != 'synthetic':
            parser.error('--data-kind real requires a labeled --csv.')
        rows = demo_rows()
        checksum = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if args.write_demo:
        if args.csv:
            parser.error('--write-demo is only for generated synthetic data.')
        args.write_demo.parent.mkdir(parents=True, exist_ok=True)
        with args.write_demo.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    try:
        result = experiment(rows, args.data_kind)
    except ValueError as exc:
        parser.error(str(exc))
    result['dataset_sha256'] = checksum
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(
        f'EXPERIMENTAL ({args.data_kind}): Accuracy={result["accuracy"]:.3f}, macro F1={result["macro_f1"]:.3f}; {args.output}'
    )


if __name__ == '__main__':
    main()

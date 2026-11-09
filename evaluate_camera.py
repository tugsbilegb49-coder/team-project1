#!/usr/bin/env python3
"""Evaluate manually labeled expected,predicted camera states without images."""

import argparse
import csv
import json
import math
from pathlib import Path

STATES = ('WORKING', 'PHONE', 'IDLE', 'AWAY')


def evaluate(rows):
    matrix = {state: {predicted: 0 for predicted in STATES} for state in STATES}
    count = 0
    for row in rows:
        actual, predicted = row['expected'], row['predicted']
        if actual not in STATES or predicted not in STATES:
            raise ValueError('Each expected/predicted state must be WORKING, PHONE, IDLE or AWAY.')
        matrix[actual][predicted] += 1
        count += 1
    if not count:
        raise ValueError('At least one manually labeled observation is required.')
    metrics = {}
    for state in STATES:
        tp = matrix[state][state]
        actual = sum(matrix[state].values())
        predicted = sum(matrix[source][state] for source in STATES)
        metrics[state] = {
            'support': actual,
            'precision': tp / predicted if predicted else None,
            'recall': tp / actual if actual else None,
        }
        denominator = actual + predicted
        metrics[state]['f1'] = 2 * tp / denominator if denominator else None
    return {
        'samples': count,
        'accuracy': sum(matrix[s][s] for s in STATES) / count,
        'per_state': metrics,
        'confusion_matrix': matrix,
    }


def boolean(value):
    if str(value).strip().lower() not in {'0', '1', 'true', 'false'}:
        raise ValueError('Presence labels must be 0/1 or true/false.')
    return str(value).strip().lower() in {'1', 'true'}


def evaluate_presence(rows):
    tp = fp = tn = fn = 0
    for row in rows:
        actual, predicted = boolean(row['expected']), boolean(row['predicted'])
        confidence = float(row['confidence'])
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('Confidence must be finite and between 0 and 1.')
        tp += actual and predicted
        fp += not actual and predicted
        tn += not actual and not predicted
        fn += actual and not predicted
    total = tp + fp + tn + fn
    if total == 0:
        raise ValueError('At least one independently labeled sample is required.')
    return {
        'samples': total,
        'accuracy': (tp + tn) / total,
        'precision': tp / (tp + fp) if tp + fp else None,
        'recall': tp / (tp + fn) if tp + fn else None,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        'specificity': tn / (tn + fp) if tn + fp else None,
        'coverage': {'present': tp + fn, 'absent': tn + fp},
        'confusion_matrix': {'TP': tp, 'FP': fp, 'TN': tn, 'FN': fn},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--mode', choices=('states', 'presence'), default='states')
    parser.add_argument('--data-kind', choices=('real', 'synthetic'), default='real')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with args.csv.open(newline='', encoding='utf-8') as source:
        rows = list(csv.DictReader(source))
    if any(row.get('data_kind', args.data_kind) != args.data_kind for row in rows):
        parser.error('CSV provenance conflicts with --data-kind.')
    result = (evaluate_presence if args.mode == 'presence' else evaluate)(rows)
    result['data_kind'] = args.data_kind
    result['label_requirement'] = 'Expected labels must be assigned by a human, independently of predictions.'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

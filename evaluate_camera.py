#!/usr/bin/env python3
"""Evaluate manually labeled expected,predicted camera states without images."""
import argparse
import csv
import json
from pathlib import Path

STATES=('WORKING','PHONE','IDLE','AWAY')


def evaluate(rows):
    matrix={state:{predicted:0 for predicted in STATES} for state in STATES}
    count=0
    for row in rows:
        actual,predicted=row['expected'],row['predicted']
        if actual not in STATES or predicted not in STATES:
            raise ValueError('Each expected/predicted state must be WORKING, PHONE, IDLE or AWAY.')
        matrix[actual][predicted]+=1
        count+=1
    if not count:
        raise ValueError('At least one manually labeled observation is required.')
    metrics={}
    for state in STATES:
        tp=matrix[state][state]
        actual=sum(matrix[state].values())
        predicted=sum(matrix[source][state] for source in STATES)
        metrics[state]={'support':actual,'precision':tp/predicted if predicted else None,'recall':tp/actual if actual else None}
    return {'samples':count,'accuracy':sum(matrix[s][s] for s in STATES)/count,'per_state':metrics,'confusion_matrix':matrix}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    args=parser.parse_args()
    with args.csv.open(newline='',encoding='utf-8') as source:
        result=evaluate(csv.DictReader(source))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

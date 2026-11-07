import copy
import pytest
from ai.experiment import demo_rows, experiment, validate_rows
from qa.agent_correctness import report


def test_random_forest_holdout_excludes_training_participants_and_is_reproducible():
    result = experiment(demo_rows())
    again = experiment(demo_rows())
    assert result == again
    assert result['status'] == 'experimental' and result['data_kind'] == 'synthetic'
    assert result['split']['participant_overlap'] == 0
    assert result['split']['train_participants'] == 3
    assert result['split']['test_participants'] == 2
    assert set(result['per_class']) == {'Low', 'Medium', 'High'}
    assert 0 <= result['accuracy'] <= 1 and 0 <= result['macro_f1'] <= 1
    assert sum(map(sum, result['confusion_matrix'])) == result['split']['test_samples']


def test_invalid_or_mislabeled_data_is_rejected():
    rows = demo_rows()
    with pytest.raises(ValueError):
        validate_rows(rows, 'real')
    for value in (float('nan'), float('inf'), -1, 2):
        invalid = copy.deepcopy(rows)
        invalid[0]['active_ratio'] = value
        with pytest.raises(ValueError):
            validate_rows(invalid, 'synthetic')
    rows[1]['sample_id'] = rows[0]['sample_id']
    with pytest.raises(ValueError):
        validate_rows(rows, 'synthetic')


def test_actual_agent_events_match_independent_expected_cases():
    result = report()
    assert result['passed'], result['cases']

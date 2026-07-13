import pytest
import ml_predictor

def test_predict_future_gpas_insufficient_semesters():
    deep_result = {
        'effective_grades': {
            'CSE-1101': {'gp': 3.5, 'credit': 3.0, 'source': 'main'}
        },
        'current_semester': 1,
        'official_semester_records': {
            1: {'gpa': 3.5, 'cgpa': 3.5}
        },
        'true_cgpa': 3.5,
        'total_credits': 3.0
    }
    # Should return None if < 2 semesters
    res = ml_predictor.predict_future_gpas(deep_result, 'CSE')
    assert res is None

def test_predict_future_gpas_success():
    deep_result = {
        'effective_grades': {
            'CSE-1101': {'gp': 3.0, 'credit': 3.0, 'source': 'main'},
            'CSE-1201': {'gp': 3.5, 'credit': 3.0, 'source': 'main'},
        },
        'current_semester': 2,
        'official_semester_records': {
            1: {'gpa': 3.0, 'cgpa': 3.0},
            2: {'gpa': 3.5, 'cgpa': 3.25}
        },
        'true_cgpa': 3.25,
        'total_credits': 6.0
    }
    
    res = ml_predictor.predict_future_gpas(deep_result, 'CSE', total_sems=4)
    
    assert res is not None
    assert 'predictions' in res
    assert 'predicted_grad_cgpa' in res
    assert 'trend_slope' in res
    
    # 2 semesters: sem 1 (3.0), sem 2 (3.5).
    # Linear slope: 0.5.
    # Sem 3 linear pred: 4.0.
    # EMA:
    # ema_0 = 3.0
    # ema_1 = 0.6 * 3.5 + 0.4 * 3.0 = 2.1 + 1.2 = 3.3
    # Sem 3 ema pred: 0.6 * 3.5 + 0.4 * 3.3 = 2.1 + 1.32 = 3.42
    # Sem 3 blended: 0.5 * 4.0 + 0.5 * 3.42 = 3.71
    # Clipped to [0, 4] -> 3.71.
    assert 3.0 <= res['predictions'][3] <= 4.0
    assert 3.0 <= res['predictions'][4] <= 4.0
    assert res['trend_slope'] == 0.5

def test_predict_future_gpas_with_overrides():
    deep_result = {
        'effective_grades': {
            'CSE-1101': {'gp': 3.0, 'credit': 3.0, 'source': 'main'},
            'CSE-1201': {'gp': 2.0, 'credit': 3.0, 'source': 'main'}, # low grade
        },
        'current_semester': 2,
        'official_semester_records': {
            1: {'gpa': 3.0, 'cgpa': 3.0},
            2: {'gpa': 2.0, 'cgpa': 2.5}
        },
        'true_cgpa': 2.5,
        'total_credits': 6.0
    }
    
    # Without overrides, slope is negative: 3.0 -> 2.0 (slope = -1.0)
    res_no_override = ml_predictor.predict_future_gpas(deep_result, 'CSE', total_sems=4)
    assert res_no_override['trend_slope'] == -1.0
    
    # With overrides: simulate clearing CSE-1201 with 3.5
    overrides = {'CSE-1201': 3.5}
    res_override = ml_predictor.predict_future_gpas(deep_result, 'CSE', total_sems=4, overrides=overrides)
    
    # Adjusted GPAs: sem 1 (3.0), sem 2 (3.5). Slope should become positive: 0.5
    assert res_override['trend_slope'] == 0.5
    assert res_override['predicted_grad_cgpa'] > res_no_override['predicted_grad_cgpa']

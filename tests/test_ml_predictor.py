import numpy as np
import pytest
from sklearn.preprocessing import RobustScaler
import ml_predictor

def test_parse_semester_from_name():
    # Test normal main exams
    assert ml_predictor.parse_semester_from_name("1st Year 1st Semester Examination of 2022") == 1
    assert ml_predictor.parse_semester_from_name("2nd Year 1st Semester Examination of 2023") == 3
    assert ml_predictor.parse_semester_from_name("3rd Year 2nd Semester Examination") == 6
    assert ml_predictor.parse_semester_from_name("4th Yr 2nd Sem'21") == 8
    
    # Test retake/improvement keyword filtering
    assert ml_predictor.parse_semester_from_name("1st Year 1st Semester Retake Examination") == 0
    assert ml_predictor.parse_semester_from_name("2nd Year 2nd Semester Improvement Exam") == 0
    assert ml_predictor.parse_semester_from_name("Special Exam of EEE") == 0
    assert ml_predictor.parse_semester_from_name("Makeup Exam of CE") == 0
    
    # Test empty or None
    assert ml_predictor.parse_semester_from_name("") == 0
    assert ml_predictor.parse_semester_from_name(None) == 0

def test_engineer_features_clipping():
    # Test clipping: momentum (3.5 -> 2.0), backlogs (10 -> 6.0)
    gpa_history = [2.0, 4.0]  # last is 4.0, prior cgpa is 2.0. Raw momentum = 4.0 - 2.0 = 2.0
    credits_history = [20.0, 20.0]
    backlogs_history = [0, 10]  # Raw backlog is 10, should clip to 6
    batch_sem_averages = {3: 3.1}
    
    features = ml_predictor.engineer_features(
        gpa_history=gpa_history,
        credits_history=credits_history,
        backlogs_history=backlogs_history,
        batch_sem_averages=batch_sem_averages,
        target_sem=3
    )
    
    assert features.shape == (6,)
    assert features[0] == 4.0  # last_gpa
    assert features[1] == 3.0  # prior_cgpa: (2.0*20 + 4.0*20)/40 = 3.0
    assert features[2] == 2.0  # momentum: 4.0 - 2.0 = 2.0 (no clipping needed here)
    assert features[3] == 3.1  # difficulty
    assert features[4] == 6.0  # backlog count: 10 clipped to 6.0
    assert features[5] == 3.0  # semester_num

    # Test extreme positive momentum clipping
    gpa_history_2 = [1.0, 4.0]  # last is 4.0, prior is 1.0. Raw momentum = 4.0 - 1.0 = 3.0 -> clipped to 2.0
    features_2 = ml_predictor.engineer_features(
        gpa_history=gpa_history_2,
        credits_history=credits_history,
        backlogs_history=[0, 0],
        batch_sem_averages=batch_sem_averages,
        target_sem=3
    )
    assert features_2[2] == 2.0  # momentum: 3.0 clipped to 2.0

    # Test extreme negative momentum clipping
    gpa_history_3 = [4.0, 1.0]  # last is 1.0, prior is 4.0. Raw momentum = 1.0 - 4.0 = -3.0 -> clipped to -2.0
    features_3 = ml_predictor.engineer_features(
        gpa_history=gpa_history_3,
        credits_history=credits_history,
        backlogs_history=[0, 0],
        batch_sem_averages=batch_sem_averages,
        target_sem=3
    )
    assert features_3[2] == -2.0  # momentum: -3.0 clipped to -2.0

def test_compute_backlog_history():
    effective_grades = {
        'CSE-1101': {'gp': 3.0, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
        'CSE-1102': {'gp': 1.5, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
        'CSE-1201': {'gp': 3.5, 'credit': 3.0, 'source': 'main', 'exam_id': '102'},
        'CSE-2101': {'gp': 3.0, 'credit': 3.0, 'source': 'retake_cleared', 'exam_id': '203'},
    }
    
    backlogs = ml_predictor.compute_backlog_history(effective_grades, 'CSE', 3)
    
    assert backlogs[1] == 0
    assert backlogs[2] == 1
    assert backlogs[3] == 1

def test_build_training_data_and_ensemble():
    deep_cache = {
        'test_profile_1001_AUTO': {
            'effective_grades': {
                'CSE-1101': {'gp': 3.5, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
                'CSE-1201': {'gp': 3.6, 'credit': 3.0, 'source': 'main', 'exam_id': '102'},
                'CSE-2101': {'gp': 3.4, 'credit': 3.0, 'source': 'main', 'exam_id': '103'},
            },
            'current_semester': 3,
            'official_semester_records': {
                1: {'gpa': 3.5, 'cgpa': 3.5},
                2: {'gpa': 3.6, 'cgpa': 3.55},
                3: {'gpa': 3.4, 'cgpa': 3.5},
            },
            'true_cgpa': 3.5,
            'total_credits': 9.0
        },
        'test_profile_1002_AUTO': {
            'effective_grades': {
                'CSE-1101': {'gp': 3.0, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
                'CSE-1201': {'gp': 2.8, 'credit': 3.0, 'source': 'main', 'exam_id': '102'},
                'CSE-2101': {'gp': 3.2, 'credit': 3.0, 'source': 'main', 'exam_id': '103'},
            },
            'current_semester': 3,
            'official_semester_records': {
                1: {'gpa': 3.0, 'cgpa': 3.0},
                2: {'gpa': 2.8, 'cgpa': 2.9},
                3: {'gpa': 3.2, 'cgpa': 3.0},
            },
            'true_cgpa': 3.0,
            'total_credits': 9.0
        }
    }
    
    X, y, batch_averages = ml_predictor.build_training_data(deep_cache, 'test_profile', 'CSE')
    
    assert len(X) == 4
    assert len(y) == 4
    assert X.shape[1] == 6
    
    models, scaler = ml_predictor.train_ensemble(X, y)
    assert len(models) == 7
    assert isinstance(scaler, RobustScaler)
    
    # Verify SVR is present
    model_names = [m['name'] for m in models]
    assert "SVR (RBF)" in model_names
    
    for m in models:
        assert 'name' in m
        assert 'model' in m
        assert 'mae' in m
        assert 'rmse' in m
        assert 'r2' in m
        assert 'needs_scaling' in m

def test_forecast_to_graduation():
    class DummyRegressor:
        def fit(self, X, y): pass
        def predict(self, features):
            return np.array([3.40])
            
    models = [
        {'name': 'Linear Regression', 'model': DummyRegressor(), 'mae': 0.15, 'rmse': 0.20, 'r2': 0.70, 'needs_scaling': True},
        {'name': 'Random Forest', 'model': DummyRegressor(), 'mae': 0.10, 'rmse': 0.15, 'r2': 0.80, 'needs_scaling': False}
    ]
    
    scaler = RobustScaler()
    # Fit scaler on dummy data
    scaler.fit(np.random.randn(10, 6))
    
    completed_gpas = [3.5, 3.8]
    completed_credits = [20.0, 20.0]
    completed_backlogs = [0, 0]
    batch_sem_averages = {3: 3.2, 4: 3.1, 5: 3.3, 6: 3.2, 7: 3.4, 8: 3.3}
    
    forecast = ml_predictor.forecast_to_graduation(
        models=models,
        scaler=scaler,
        completed_gpas=completed_gpas,
        completed_credits=completed_credits,
        completed_backlogs=completed_backlogs,
        batch_sem_averages=batch_sem_averages,
        start_sem=3,
        total_sems=8
    )
    
    ensemble_forecast = forecast['ensemble_forecast']
    model_forecasts = forecast['model_forecasts']
    
    assert len(ensemble_forecast) == 6
    for sem in range(3, 9):
        assert sem in ensemble_forecast
        assert round(ensemble_forecast[sem], 2) == 3.40
        assert round(model_forecasts['Linear Regression'][sem], 2) == 3.40

import numpy as np
import pytest
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

def test_engineer_features():
    gpa_history = [3.5, 3.8, 3.2]
    credits_history = [20.0, 20.0, 20.0]
    backlogs_history = [0, 1, 0]
    batch_sem_averages = {4: 3.1}
    
    features = ml_predictor.engineer_features(
        gpa_history=gpa_history,
        credits_history=credits_history,
        backlogs_history=backlogs_history,
        batch_sem_averages=batch_sem_averages,
        target_sem=4
    )
    
    # Feature vector size should be 6: last_gpa, prior_cgpa, gpa_momentum, difficulty, backlog_count, semester_num
    assert features.shape == (6,)
    assert features[0] == 3.2  # last_gpa
    assert round(float(features[1]), 2) == 3.5  # prior_cgpa: (3.5*20 + 3.8*20 + 3.2*20)/60 = 3.5
    assert round(float(features[2]), 2) == -0.3  # momentum: 3.2 - 3.5 = -0.3
    assert features[3] == 3.1  # difficulty of sem 4
    assert features[4] == 0.0  # backlog count at start of target sem (last elem of backlogs_history)
    assert features[5] == 4.0  # semester_num

def test_compute_backlog_history():
    # Mock effective_grades where:
    # CSE-1101 (Sem 1): gp 3.0, main exam
    # CSE-1102 (Sem 1): gp 1.5, main exam (backlog!)
    # CSE-1201 (Sem 2): gp 3.5, main exam
    # CSE-2101 (Sem 3): gp 3.0, cleared via retake later (main exam had backlog)
    effective_grades = {
        'CSE-1101': {'gp': 3.0, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
        'CSE-1102': {'gp': 1.5, 'credit': 3.0, 'source': 'main', 'exam_id': '101'},
        'CSE-1201': {'gp': 3.5, 'credit': 3.0, 'source': 'main', 'exam_id': '102'},
        'CSE-2101': {'gp': 3.0, 'credit': 3.0, 'source': 'retake_cleared', 'exam_id': '203'},
    }
    
    # Compute backlog history for CSE (current_semester = 3)
    backlogs = ml_predictor.compute_backlog_history(effective_grades, 'CSE', 3)
    
    # Semester 1: no completed semesters, 0 backlogs
    assert backlogs[1] == 0
    # Semester 2: completed Sem 1. CSE-1102 is failing (gp 1.5). Backlog = 1.
    assert backlogs[2] == 1
    # Semester 3: completed Sem 1 & 2. CSE-1102 is still failing (gp 1.5). CSE-2101 belongs to sem 3. Backlog = 1.
    assert backlogs[3] == 1

def test_build_training_data_and_ensemble():
    # Mock a deep cache with 3 students having 3 semesters of data
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
    
    # 2 students, current_semester = 3. Sliding windows (t=2, 3) -> 2 samples per student -> 4 total training samples
    assert len(X) == 4
    assert len(y) == 4
    assert X.shape[1] == 6
    
    # Check ensemble training
    models = ml_predictor.train_ensemble(X, y)
    assert len(models) == 6
    for m in models:
        assert 'name' in m
        assert 'model' in m
        assert 'mae' in m
        assert 'rmse' in m
        assert 'r2' in m

def test_forecast_to_graduation():
    # Dummy models configuration
    class DummyRegressor:
        def fit(self, X, y): pass
        def predict(self, features):
            # Returns a constant prediction of 3.40
            return np.array([3.40])
            
    models = [
        {'name': 'Linear Regression', 'model': DummyRegressor(), 'mae': 0.15, 'rmse': 0.20, 'r2': 0.70},
        {'name': 'Random Forest', 'model': DummyRegressor(), 'mae': 0.10, 'rmse': 0.15, 'r2': 0.80}
    ]
    
    completed_gpas = [3.5, 3.8]
    completed_credits = [20.0, 20.0]
    completed_backlogs = [0, 0]
    batch_sem_averages = {3: 3.2, 4: 3.1, 5: 3.3, 6: 3.2, 7: 3.4, 8: 3.3}
    
    forecast = ml_predictor.forecast_to_graduation(
        models=models,
        completed_gpas=completed_gpas,
        completed_credits=completed_credits,
        completed_backlogs=completed_backlogs,
        batch_sem_averages=batch_sem_averages,
        start_sem=3,
        total_sems=8
    )
    
    ensemble_forecast = forecast['ensemble_forecast']
    model_forecasts = forecast['model_forecasts']
    
    # Predicted semesters should range from 3 to 8
    assert len(ensemble_forecast) == 6
    for sem in range(3, 9):
        assert sem in ensemble_forecast
        assert round(ensemble_forecast[sem], 2) == 3.40
        assert round(model_forecasts['Linear Regression'][sem], 2) == 3.40

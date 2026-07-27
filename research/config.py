"""
research/config.py — Centralized Configurable Thresholds & Parameters
All empirical constants and algorithm parameters for research sensitivity analysis.
"""

THRESHOLDS = {
    # Re-admission detection (auto_pdf_mailer.py + v2_auto_sync.py)
    "readd_overlap_min": 0.50,          # overlap_ratio >= 0.5
    "readd_load_min": 0.70,             # subject_load_ratio >= 0.7 (DUAL FILTER)
    "readd_freq_min": 0.30,             # min_freq = valid_student_count * 0.3
    "readd_subject_min_count": 4,       # len(subjects) >= 4

    # GPA forecasting (ml_predictor.py)
    "prediction_ema_alpha": 0.6,        # alpha = 0.6
    "prediction_blend_weight": 0.5,     # 0.5 * linear + 0.5 * EMA

    # Database (database.py)
    "gpa_cap": 4.0,                     # _parse_gp: min(val, 4.0)

    # Networking (cli_scraper.py on v2)
    "network_timeout_sec": 15,          # session.get/post timeout=15
    "network_retries": 4,               # make_request retries=4
    "backoff_global_sec": 15.0,         # global_backoff_until = time.time() + 15.0

    # Monitoring (exam_monitor cron)
    "monitor_poll_interval_min": 15,    # GitHub Actions schedule

    # Academic thresholds (pages/analytics.py)
    "promotion_thresholds": {1: 2.00, 2: 2.25, 3: 2.50},  # get_promotion_rules()
    "high_performer_cgpa": 3.75,
    "at_risk_delta": -0.25,
}

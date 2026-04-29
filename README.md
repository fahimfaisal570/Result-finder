# Result Finder PRO

Result Finder PRO is a web-based academic result aggregation and analysis platform for Faridpur Engineering College. It organizes scattered DUCMC result data into structured, batch-wise views so students can inspect current and past results, track academic progress, and review standings such as semester rankings, scholarship eligibility, and CGPA.  

## Overview

This branch is the stable core of the project.

It focuses on:
- result discovery and scraping
- exam filtering and selection
- student history and saved batch workflows
- batch-wise analytics and result presentation
- exam monitoring and automation support

The application combines a Streamlit dashboard with a command-line scraping engine, while the scraper itself is split across dedicated core modules for networking, profiles, parsing, and reports.

## What this branch does

`main` is built for reliable production use. It supports:
- interactive program and session discovery from the DUCMC portal
- exam selection with main-batch and senior re-add handling
- multi-range batch submission in a single scan
- saved profile persistence
- result analysis through the dashboard
- exam monitoring utilities for keeping track of new or updated exams

## Architecture

The codebase is organized into distinct layers:

### Dashboard layer
`app.py` provides the Streamlit interface for interactive scanning and saved-profile workflows.

### Scraping layer
`cli_scraper.py` acts as the core scraper and CLI interface. It imports from `scraper_core.network`, `scraper_core.profiles`, `scraper_core.parser`, and `scraper_core.reports`, which keeps the scraping logic separated from the UI.

### Monitoring layer
`exam_monitor/` contains automation and synchronization utilities, including:
- `auto_pdf_mailer.py`
- `find_latest.py`
- `monitor.py`
- `sync_state.py`
- `known_exams.json`

### Presentation layer
`pages/` contains dashboard pages for result browsing and analysis.

## Key features

- Portal-based program and session discovery
- Exam filtering for relevant result sets
- Main batch and senior re-add handling
- Multi-range scan payload generation
- Saved batch/profile support
- CLI-native scraping for automation and low-friction execution
- Streamlit dashboard for visual inspection of results
- Exam monitoring utilities for recurring workflows

## Why this branch matters

This branch is the stable reference implementation.  
It is the branch to use when you want:
- predictable behavior
- a simpler runtime surface
- the main result discovery and result-generation workflow
- a cleaner core without the extra experimental layers in `v2`

## Project structure

- `app.py` — Streamlit dashboard entry point
- `cli_scraper.py` — CLI scraper and scraping engine
- `scraper_core/` — core network, profile, parser, and report modules
- `exam_monitor/` — monitoring and auto-mailing utilities
- `pages/` — dashboard pages
- `requirements.txt` — Python dependencies
- `saved_profiles.json` — persisted batch/profile data
- `system_cache.json` — runtime cache

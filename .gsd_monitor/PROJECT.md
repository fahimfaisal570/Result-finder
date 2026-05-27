# Project Name: FEC Exam Publication Monitor
This workflow runs as a high-frequency background task (cron: every 10 minutes) on GitHub Actions, dynamically checking the central university portal for new exam result publication events. If found, it routes real-time alerts to administrators/heads, generates automated PDF batch reports, and triggers database cross-syncing to the analytics dashboard.

## Core Tech Stack
- **Language**: Python 3.10+
- **HTTP client**: Zero-dependency `urllib.request` (optimized for lightweight environment boot and check-only phases)
- **Email delivery**: Standard standard library `smtplib` (SSL encrypted via SMTP Gmail)
- **PDF Engine**: `pdfkit` + `wkhtmltopdf` (loaded lazily only if a publication occurs)
- **Execution Environment**: GitHub Actions runner (`ubuntu-latest` running inside `xvfb` virtual framebuffer)

## Development Conventions
- **Zero-Dependency Fast Boot**: Fast checking `monitor.py --check-only` must never import heavy packages (like `pdfkit`, `jinja2`, or `requests`) to keep action runtime minimal.
- **Compiled Regex Optimizations**: Pre-compile all HTML parsing and option parsing patterns at the module level.
- **Dynamic Scraper Interception**: Leverage runtime monkeypatching to override standard timing constraints in the parent scraper engine during automated scans.

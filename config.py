# Configuration for Auto-Scanner Scheduler

# How often to run the full auto-scan cycle (in minutes). 
# Default: 30 minutes. Be respectful of the university server.
SCAN_INTERVAL_MINUTES = 30

# Maximum number of concurrent scraper threads. 
# Keep it low to prevent IP blocks/strains on the server.
THREADS_PER_SCAN = 5

# Which profiles to scan automatically. 
# Leave as empty list [] to scan ALL profiles in the database.
# E.g., SCAN_ONLY_PROFILES = ["cse 09", "eee 10"]
SCAN_ONLY_PROFILES = []

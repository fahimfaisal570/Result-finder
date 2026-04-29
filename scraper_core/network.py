from __future__ import print_function
import os
import sys
import time
import datetime
def get_bd_time():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=6)
import re
import ssl
import subprocess
import collections
import random

# --- Python 2/3 Compatibility Shims ---
if sys.version_info[0] < 3:
    import urllib2 as urllib_req
    import urllib as urllib_parse
    import Queue as queue
    input_func = raw_input
else:
    import urllib.request as urllib_req
    import urllib.parse as urllib_parse
    import queue
    input_func = input
import json
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx, add_report_ctx
except ImportError:
    get_script_run_ctx = add_report_ctx = lambda *args, **kwargs: None

import threading

# --- Scraper Configuration ---
BASE_URL = "https://ducmc.du.ac.bd/"
AJAX_URL = "https://ducmc.du.ac.bd/ajax/get_program_by_exam.php"
PROGRAM_AJAX_URL = "https://ducmc.du.ac.bd/ajax/get_program_by_course.php"
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
]

# Shared Caches (for Web Dashboard integration)
SESSIONS_CACHE = {}
PROGRAMS_CACHE = {}
SESSION_HINTS = {} # {(pro_id, exam_id): sess_id} - Speeds up "AUTO" session discovery

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Origin': 'https://ducmc.du.ac.bd',
    'Referer': 'https://ducmc.du.ac.bd/result.php',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'X-Requested-With': 'XMLHttpRequest'
}

# Session Globals
SESSION_UA = random.choice(USER_AGENTS)
SESSION_COOKIES = {}

# Robust path resolution for Android persistence
ORIGINAL_DIR = os.getcwd()
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ORIGINAL_DIR

try:
    ssl_context = ssl._create_unverified_context()
except AttributeError:
    ssl_context = None

# --- HTTP Keep-Alive Connection Pool ---
if sys.version_info[0] < 3: import httplib as http_client
else: import http.client as http_client

class KeepAlivePool:
    def __init__(self, host, pool_size=100):
        self.host = host
        self.pool = queue.Queue(maxsize=pool_size)
        self.pool_size = pool_size
        self.lock = threading.Lock()
        self.created = 0
    def get_connection(self):
        try: return self.pool.get_nowait()
        except queue.Empty:
            with self.lock:
                if self.created < self.pool_size:
                    self.created += 1
                    kwargs = {}
                    if ssl_context: kwargs['context'] = ssl_context
                    return http_client.HTTPSConnection(self.host, timeout=15, **kwargs)
            return self.pool.get(block=True)
    def return_connection(self, conn):
        try: self.pool.put_nowait(conn)
        except queue.Full: conn.close()

# Global connection pool for the target domain
http_pool = KeepAlivePool("ducmc.du.ac.bd", pool_size=100)
last_successful_session = None
global_backoff_until = 0

_stealth_lock = None
_cookie_lock = None

def get_stealth_lock():
    global _stealth_lock
    if _stealth_lock is None:
        _stealth_lock = threading.Lock()
    return _stealth_lock

def get_cookie_lock():
    global _cookie_lock
    if _cookie_lock is None:
        _cookie_lock = threading.Lock()
    return _cookie_lock

def make_request(url, data=None, headers=None, retries=4):
    """Makes HTTP requests with full session awareness (Cookies + Pinned UA)."""
    req_headers = HEADERS.copy()
    req_headers['User-Agent'] = SESSION_UA
    
    with get_cookie_lock():
        if SESSION_COOKIES:
            cookie_str = "; ".join(["{0}={1}".format(k, v) for k, v in SESSION_COOKIES.items()])
            req_headers['Cookie'] = cookie_str
            
    if headers: req_headers.update(headers)
    
    encoded_data = None
    method = "GET"
    if data:
        method = "POST"
        encoded_data = urllib_parse.urlencode(data)
        if type(encoded_data) is str: encoded_data = encoded_data.encode('utf-8')
        req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    parsed_url = urllib_parse.urlparse(url)
    path = parsed_url.path
    if parsed_url.query: path += "?" + parsed_url.query
        
    for attempt in range(retries):
        conn = http_pool.get_connection()
        try:
            # Added explicit 15s timeout to prevent 'stuck' threads
            conn.timeout = 15
            conn.request(method, path, body=encoded_data, headers=req_headers)
            response = conn.getresponse()
            
            # Extract cookies if present
            set_cookie = response.getheader('Set-Cookie')
            if set_cookie:
                with get_cookie_lock():
                    parts = set_cookie.split(';')[0].split('=')
                    if len(parts) >= 2:
                        SESSION_COOKIES[parts[0].strip()] = parts[1].strip()
            
            if response.status in (200, 301, 302):
                raw_data = response.read()
                try:
                    out = raw_data.decode('utf-8')
                except UnicodeDecodeError:
                    out = raw_data.decode('latin-1', 'ignore')
                
                if response.getheader('Connection', '').lower() == 'close': conn.close()
                return out
            else:
                conn.close()
        except Exception:
            conn.close()
        finally:
            http_pool.return_connection(conn)
                 
        time.sleep(min(5.0, 1.0 + attempt)) # Light backoff
            
    return None


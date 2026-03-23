import streamlit as st
import pandas as pd
import os
import sys
import time
import re
import ssl
import collections
import random
import threading
import queue
import urllib.request as urllib_req
import json
import cli_scraper as cs

# --- Session State Initialization ---
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# --- Helper: Logo Base64 ---
def get_base64_logo(file_path):
    import base64
    if not os.path.exists(file_path): return ""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# --- Single Source of Truth Logic (from cli_scraper) ---
classify_exams = cs.classify_exams
fetch_exams = cs.fetch_exams
fetch_student_result = cs.fetch_student_result
format_session = cs.format_session
parse_range_string = cs.parse_range 
make_request = cs.make_request
extract_options_from_html = cs.extract_options_from_html
BASE_URL = cs.BASE_URL
AJAX_URL = cs.AJAX_URL
SESSIONS_CACHE = cs.SESSIONS_CACHE
PROGRAMS_CACHE = cs.PROGRAMS_CACHE

# Patch cs to ensure it doesn't try to run main() on import
# (Though its main() is already guarded by if __name__ == "__main__")

def parse_range_string(range_str):
    results = []
    if not range_str: return []
    parts = [p.strip() for p in range_str.split(',') if p.strip()]
    for part in parts:
        if '-' in part:
            try:
                start, end = part.split('-')
                results.extend(range(int(start), int(end) + 1))
            except: pass
        else:
            try: results.append(int(part))
            except: pass
    return sorted(list(set(results)))

LOGO_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAMgAAADICAYAAACtWK6eAADf50lEQVR4nOy9B5gcV5U2/FZ17p6ccw6aUc45WHKSszG2wQYMmLiwwEfwLj8s3m+BXZLBwC4ZbGPAgHGOki1bVrByTiNNzqGnc+6u7vqfc6qquydJMsi74ltfP2NN91S89557T3jPe4B32jvtnfZOe6e9095p77R32jvtnfZOe6e9095p77R32jvtnfZOe6f9HTfhf/oB3mnABz7wgfI777z93c3NTRsyM7PzR0aG7eNj48/89ne/2/rII4+MvNNH77T/le0977mp7NVXX/233t6eYVmW5PQWT0Tlnr6uwaeffvL+xYsXF/xPP+s77Z3239nMTzzxxKc6Os71JSUikZggILIcT/7b1nbm3J///Ni9AHTvDNM77f/p9uSTj9/Q2d2xV5KimmTw/8fDXvnpo9vkB19+VH7h5G7ZHQlMEJRINCyfOXN61+9+9/AV/9Pv8E57p13y9u1vf3P94cOHnvP5POpWofzjjwflJ4+/Jt/w/U/Kxf+4Ts769Eq57HNXyLc8+Gn5uRPb5UhioiC5XOPSzp07nv6P//i3he8M09vf3jHS3+b21a/eN/uGG275Qk119QeKS8pUFUlGDDJ2dxzBL7c9jh3tBxAQJeh0OggQlSNiEqyiGVfPWoWPXnk7llTNgpg2XKOjQ4GjR4/+buvWbd/8/ve/3/92v8f/1vaOgLxN7cMf/nDZPfe8/1MNDQ2fKiuryNa+lwEcHjqLh7Y/hReOvAGfFIBoMkAQJw2FDMiyDCkaR5ExCzct2YiPrL8NTYWVEw4bGuwfOXL06C9/8pMHfvLii2+84/G6xO0dAbnEra6uLvtXv/r5Pc3Nsz5fVlZRrXybACCiwz2E377+JP64fwvGom7o9XqIOtoXpg4DCZIAGXHIkONxJCJx1GSU4u71N+C9KzejPKMoeRS17u6O7jPnznz9+mtv+h2A2KV+r/+t7R0BuXTN8NBDv7pj4aKF98+ft6CRBEITjKGwE0/t3YZH3ngSHc5+6MwGQCcmVSZZkCHIaYMiAwlR+ZdaQlZ+SSRkCJEYWotq8aEr3o1bF29EjjEzeV5MiuDc2fa9b+7c9a2PffKTz1zCd/tf294RkEvQfvKLn2xcs2LV/9fQUL/JYslIfu+LB/DSsZ349bYncGS4HZIREHU66OTpuj1NQqZtMv9HLS7FYZRELKtqxb2bbsemOatgE0zJI91uFzrOnXtu66vbvvuVr3xl56V4x/+t7R0B+RvaAw/8x/xNV171xYqKqrvz8woFTeWJIYHtZ/fjF9v+iN3dxxEW49DraEsQIMjKD+0aE4fhwgJCKpfym/ITkxLIkA1Y37QEn7zyvVhZO18z8fmao6OjsaGhgV/v2bPv3z/1qU+9Y8j/Fe0dAfkr2vvf//6qT3ziY59qaKj/VFFRqU35VkYCAg4OnsGvtz6Ol0/vhk8IQ6c3KELBPU2qlIypG8iFBYTOmSBT6ndIJCDFJOSJNty8eBM+eMVtmFtUN+G4sbHHsX379v7qwZ//509ee+G1wb/mnf+3tncE5C20uXPn5n7zm9+8t7W1+b76+qbC9L+ddQ7gt689hScPboU94oFoNkBQpEKdydTbZJO8PS0uxyGHYii1FeH2FZvxwbU3oTqnZMIxbWfPDJw4fvw7d9zxnodJA3zbHub/ofaOgFxc0z377FN3NjW13N/U1NSkTHxFjRkOOPDHXS/i0TefR7dnGDqTCJ0oQhbSoxZak9/ikFzM8akjyS1MHi85KqMxtxL3bLgVd6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcJGCg8JbFZSZYyjkCEjEErDKelzRtAQf3fQeLK+bBwO/s3LUmH3U19HesTcUCsr0Wacyed6y4GvmmrOTzxuMxtLd3Ht2/f/+37rnnnsdVT8I7bYb2joBcoP3oR9+/8qqrrv2nurraK41Gc/J7vxTEs4dfwy9fexwnR7ogmUToRT3IN6X0avrklqdVkS48DBcvIMlrJGQkBCCeiEMfF7CsZBY+dtWduHLeSljZkFcEJRDwob2zY8ue/Xu/8g8f/YdDb+FG/6vapRYQ3U9+8pPblyxZtNLpGm+GTEutCFGceDv6Nhkx1v6iqSMTmgwxLYCWSEC9VmoyJJuYOgaqW5QO037VXK6ppi2c6nPIyudEIg6TyeRLJORDgoDa2bPnfKSoqCT5EBE5ildPH8BvXnsC+3uPIqyPQxT1aV2Zbk9ov2s/wnlNcH/9k="

# --- Page Config ---
st.set_page_config(page_title="Result Finder", page_icon="🎓", layout="wide")

# Page Branding & Layout
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif;
    }
    
    footer {visibility: hidden;}
    [data-testid="stSidebarNav"] { display: none !important; }
    
    .metric-card {
        border: 1px solid var(--secondary-background-color);
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 20px;
        background-color: var(--background-color);
        color: var(--text-color);
    }
      /* Premium Floating Elevations */
    div[data-testid="stSelectbox"] > div {
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        border: 1px solid var(--border) !important;
    }
    div[data-testid="stSelectbox"]:hover > div {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(59, 130, 246, 0.3);
        border-color: var(--primary-color) !important;
    }
    
    /* Hover Open Hint */
    div[data-testid="stSelectbox"]::after {
        content: '✨ Hover to Open';
        position: absolute;
        top: -15px;
        right: 0;
        font-size: 0.6em;
        opacity: 0;
        transition: opacity 0.3s;
        color: var(--primary-color);
        pointer-events: none; /* Crucial: don't block mouse events */
    }
    div[data-testid="stSelectbox"]:hover::after {
        opacity: 0.8;
    }
</style>

<script>
    (function() {
        const doc = window.parent.document;
        const trigger = (el) => {
            ['mousedown', 'mouseup', 'click'].forEach(name => {
                const evt = new MouseEvent(name, { bubbles: true, cancelable: true, view: window.parent });
                el.dispatchEvent(evt);
            });
        };

        const handleHover = (e) => {
            const selectbox = e.target.closest('div[data-testid="stSelectbox"]');
            if (selectbox && !selectbox.dataset.hoverLock) {
                 const btn = selectbox.querySelector('div[role="button"]') || selectbox.querySelector('input');
                 const isOpen = !!doc.querySelector('div[role="listbox"]');
                 
                 if (btn && !isOpen) {
                     // Instant Trigger
                     trigger(btn);
                     
                     // Lock to prevent multi-pops
                     selectbox.dataset.hoverLock = "true";
                     setTimeout(() => { selectbox.dataset.hoverLock = ""; }, 500);
                 }
            }
        };

        doc.addEventListener('mouseover', handleHover);
    })();
</script>
<p style="display:none; opacity:0; pointer-events:none;">Interaction Guard</p>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .exam-card {
        cursor: pointer;
        transition: all 0.2s ease;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .exam-card:hover {
        background: var(--background-color);
        border-color: var(--primary-color);
        transform: translateX(5px);
    }
    .exam-card-active {
        background: var(--secondary-background-color) !important;
        border: 2px solid var(--primary-color) !important;
        box-shadow: 0 4px 12px rgba(0, 102, 204, 0.1);
    }
    .exam-title {
        font-weight: 600;
        color: var(--text-color);
        font-size: 0.95em;
    }
    .exam-tag {
        font-size: 0.75em;
        text-transform: uppercase;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: 700;
    }
    .tag-main { background: #dcfce7; color: #166534; }
    .tag-other { background: #f3f4f6; color: #4b5563; }
    /* Compact Exam Cards */
    .stButton > button {
        border-radius: 8px !important;
        text-align: left !important;
        padding: 0.5rem 1rem !important;
        font-size: 0.85rem !important;
        border: 1px solid var(--secondary-background-color) !important;
        background: var(--background-color) !important;
        color: var(--text-color) !important;
        transition: all 0.2s ease !important;
        justify-content: flex-start !important;
    }
    .stButton > button:hover {
        border-color: var(--primary-color) !important;
        background: var(--secondary-background-color) !important;
        color: var(--primary-color) !important;
        transform: translateX(4px);
    }
    .stButton > button[kind="primary"] {
        background: var(--primary-color) !important;
        border: 2px solid var(--primary-color) !important;
        color: white !important;
        font-weight: 700 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Interactive Scan & Logic Blocks ---
def fetch_programs_and_sessions():
    html = make_request(BASE_URL)
    if not html: return {}, {}
    programs = collections.OrderedDict()
    sessions = collections.OrderedDict()
    select_blocks = re.findall(r'<select.*?</select>', html, re.DOTALL | re.IGNORECASE)
    for block in select_blocks:
        options = extract_options_from_html(block)
        if not options: continue
        first_opt_text = options[0][1].lower() if options else ""
        if 'session' in first_opt_text:
            for val, text in options: sessions[val] = text
        elif 'course name' in first_opt_text:
            categories = [o[0] for o in options if o[0] != "0"]
            for cat_id in categories:
                cat_url = f"{BASE_URL}ajax/get_program_by_course.php?course_id={cat_id}"
                cat_html = make_request(cat_url)
                if cat_html:
                    p_opts = extract_options_from_html(cat_html)
                    for p_val, p_text in p_opts:
                        if p_val != "0": programs[p_val] = p_text
    
    # Apply Sorting, Formatting, and Discipline Filtering
    if programs:
        whitelist = ["computer science", "civil engineering", "electrical and electronic"]
        filtered = {k: v for k, v in programs.items() if "b.sc." in v.lower() and any(w in v.lower() for w in whitelist)}
        programs = collections.OrderedDict(sorted(filtered.items(), key=lambda x: x[1]))
    
    if sessions:
        formatted = []
        for sid, sname in sessions.items():
            f_name = format_session(sname)
            # Filter: only keep sessions starting from 2016-17 onwards
            # Search in the ORIGINAL name which has the 4-digit year
            year_match = re.search(r"(20\d{2})", sname)
            if year_match:
                start_year = int(year_match.group(1))
                if start_year >= 2016:
                    formatted.append((sid, sname)) # Keep original sname for cs.sessions_cache
        
        formatted.sort(key=lambda x: x[1], reverse=True)
        sessions = collections.OrderedDict(formatted)
        SESSIONS_CACHE.update(sessions) # Populate shared cache

    return programs, sessions

# --- End of Logic ---

fetch_student_result = cs.fetch_student_result
parse_range_string = cs.parse_range # Re-use the robust range parser from CLI

class BatchManager:
    def __init__(self):
        self.filename = "saved_profiles.json"
        
    def load_profiles(self):
        try:
            with open(self.filename, 'r') as f:
                data = json.load(f)
                return data if data else {}
        except (json.JSONDecodeError, ValueError, Exception, FileNotFoundError):
            return {}
        
    def save_new_batch(self, name, results_list, pro_id, exam_id):
        profiles = self.load_profiles()
        regs_data = [[int(r['Reg']), "AUTO", r['Name']] for r in results_list]
        profiles[name] = {
            "regs": regs_data,
            "pro_id": pro_id,
            "latest_exam_id": exam_id,
            "timestamp": time.time()
        }
        try:
            with open(self.filename, 'w') as f:
                json.dump(profiles, f, indent=4)
            return True
        except: return False

batch_manager = BatchManager()

def scraper_worker(q, pro_id, sess_id, exam_id, results, progress_bar, total):
    while not q.empty():
        reg = q.get()
        res = fetch_student_result(reg, pro_id, sess_id, exam_id)
        if res: results.append(res)
        q.task_done()
        progress_bar.progress(1 - q.qsize() / total)

# --- Streamlit UI ---
st.title("🎓 Result Finder")
st.markdown("A premium, high-performance web dashboard for academic result analytics.")

# Initialization
if 'programs' not in st.session_state:
    with st.spinner("Connecting to portal..."):
        st.session_state.programs, st.session_state.sessions = fetch_programs_and_sessions()

# --- Branding & Header ---
HOVER_OPEN_JS = """
<script>
    (function() {
        const targetDoc = (window.parent && window.parent.document) ? window.parent.document : document;
        const trigger = (el) => {
            ['mousedown', 'mouseup', 'click'].forEach(n => {
                el.dispatchEvent(new MouseEvent(n, { bubbles: true, cancelable: true, view: window.parent || window }));
            });
        };
        const onHover = (e) => {
            const selectbox = e.target.closest('div[data-testid="stSelectbox"]');
            if (selectbox && !selectbox.dataset.hoverLock) {
                const btn = selectbox.querySelector('div[role="button"]') || selectbox.querySelector('input');
                // Check listbox in both local and parent doc
                const isOpen = !!document.querySelector('div[role="listbox"]') || !!targetDoc.querySelector('div[role="listbox"]');
                if (btn && !isOpen) {
                    trigger(btn);
                    selectbox.dataset.hoverLock = "true";
                    setTimeout(() => { selectbox.dataset.hoverLock = ""; }, 500);
                }
            }
        };
        targetDoc.addEventListener('mouseover', onHover);
    })();
</script>
"""

# Apply to Main
st.markdown(HOVER_OPEN_JS, unsafe_allow_html=True)

# Sidebar - Mode Selection
with st.sidebar:
    # Apply to Sidebar
    st.markdown(HOVER_OPEN_JS, unsafe_allow_html=True)
    
    # Centered and Higher Logo (Refined to prevent clipping)
    logo_file = "college_logo.png"
    if os.path.exists(logo_file):
        b64 = get_base64_logo(logo_file)
        st.markdown(f"""
            <div style="display: flex; justify-content: center; margin-top: -75px; margin-bottom: 20px; width: 100%;">
                <img src="data:image/png;base64,{b64}" style="width: 175px; height: auto; margin: 0 auto;">
            </div>
        """, unsafe_allow_html=True)
    else:
        st.title("🎓 Result Finder")
    
    st.write("") # Tiny spacer
    mode = st.radio("App Mode", ["Interactive Scan", "Saved Profiles"], index=1, horizontal=True)

    def trigger_scan():
        st.session_state.trigger_fetch = True

if mode == "Interactive Scan":
    # Sidebar - Configuration
    with st.sidebar:
        if not st.session_state.programs:
            st.error("Portal Unreachable")
            if st.button("Retry Connection"):
                st.session_state.programs, st.session_state.sessions = fetch_programs_and_sessions()
                try: st.rerun()
                except AttributeError: st.experimental_rerun()
            st.markdown('<h3 style="margin-bottom: -10px;">⚙️ Settings</h3>', unsafe_allow_html=True)
        
        # Program Selection
        p_list = list(st.session_state.programs.values())
        program_name = st.selectbox("Program", options=p_list if p_list else ["No Programs"], key="sb_prog")
        pro_id = [k for k, v in st.session_state.programs.items() if v == program_name][0] if p_list and program_name != "No Programs" else None
        
        # Session Selection
        s_list = list(st.session_state.sessions.values())
        if not s_list:
            st.warning("⚠️ No sessions found (2016+ filter).")
            st.stop()
            
        session_name = st.selectbox("Session", options=s_list, key="sb_sess")
        sess_id = [k for k, v in st.session_state.sessions.items() if v == session_name][0]
        
        # Exam Selection
        exams_raw = fetch_exams(pro_id) if pro_id else {}
        if not exams_raw:
            st.error("❌ No examinations found for this program.")
            st.stop()
            
        mains, others = classify_exams(exams_raw, session_name)
        exam_type = st.radio("Exam Category", ["Main Exams", "Retake / All Exams"], horizontal=True, key="sb_type")
        
        if exam_type == "Main Exams" and mains:
            exam_name = st.selectbox("Examination", options=list(mains.values()), key="sb_exam_main", on_change=trigger_scan)
            exam_id = [k for k, v in mains.items() if v == exam_name][0]
        else:
            exam_name = st.selectbox("Examination (All)", options=list(exams_raw.values()), key="sb_exam_all", on_change=trigger_scan)
            exam_id = [k for k, v in exams_raw.items() if v == exam_name][0]

    # Main Area - Dynamic Range Selection
    st.markdown('<div class="metric-card">', unsafe_allow_html=True)
    st.header("🔍 Start New Scan")
    
    # Initialize Re-adds in state
    if 'ra_items' not in st.session_state:
        st.session_state.ra_items = []

    import json, base64
    from urllib.parse import quote as _quote

    # 1. Main Batch (Fixed to Sidebar Session)
    st.markdown(f"### 📦 Main Batch ({session_name})")
    col_m1, col_m2 = st.columns([3, 1])
    with col_m1:
        main_range = st.text_input("Registration Numbers", placeholder="e.g., 210101-210150", key="main_range_input")
    with col_m2:
        st.caption("Primary Session")
        st.info(session_name)
    
    st.write("")
    
    # 2. Senior Re-adds (Manual Entry)
    st.markdown("### ➕ Senior Re-adds (Discovery)")
    if not st.session_state.ra_items:
        st.caption("No senior batches added yet. Click below to add re-add candidates.")
    
    to_delete = []
    for i, ra in enumerate(st.session_state.ra_items):
        r_col1, r_col2, r_col3 = st.columns([2, 2, 0.5])
        with r_col1:
            ra['range'] = st.text_input(f"Range {i+1}", value=ra['range'], key=f"ra_range_{i}", placeholder="e.g. 850-900")
        with r_col2:
            s_options = list(st.session_state.sessions.values())
            # Find index of current ra['sess'] in options
            s_idx = s_options.index(ra['sess']) if ra['sess'] in s_options else 0
            ra['sess'] = st.selectbox(f"Session {i+1}", options=s_options, index=s_idx, key=f"ra_sess_{i}")
        with r_col3:
            st.write("") # padding
            if st.button("🗑️", key=f"ra_del_{i}"):
                to_delete.append(i)
    
    if to_delete:
        for idx in sorted(to_delete, reverse=True):
            st.session_state.ra_items.pop(idx)
        st.rerun()

    if st.button("➕ Add Senior Batch Range"):
        st.session_state.ra_items.append({'range': '', 'sess': session_name})
        st.rerun()

    st.write("---")

    # 3. Execution (Build Payload)
    if exam_id and (main_range or st.session_state.ra_items):
        # Construct [[range, sess_id], ...]
        batch_payload = []
        if main_range:
            batch_payload.append([main_range, sess_id])
        
        for ra in st.session_state.ra_items:
            if ra['range']:
                # Resolve ra_sess_id from name
                ra_sid = [k for k, v in st.session_state.sessions.items() if v == ra['sess']][0]
                batch_payload.append([ra['range'], ra_sid])
        
        if batch_payload:
            payload_str = base64.b64encode(json.dumps(batch_payload).encode()).decode()
            res_url = f"/results?pro_id={pro_id}&exam_id={exam_id}&exam_name={_quote(exam_name)}&payload={payload_str}"
            
            st.markdown(f"""
            <a href="{res_url}" target="_blank" style="text-decoration: none;">
                <button style="
                    background: var(--primary-color); color: white; border: none; padding: 12px 24px;
                    border-radius: 8px; font-weight: 600; cursor: pointer; display: flex;
                    align-items: center; gap: 8px; width: 100%; justify-content: center;
                ">
                🚀 Run Scraper & View Results ({len(batch_payload)} Batches)
                </button>
            </a>
            """, unsafe_allow_html=True)
        else:
            st.button("🚀 Run Scraper", disabled=True, use_container_width=True)
    else:
        st.button("🚀 Run Scraper (Provide Range)", disabled=True, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

else: # Saved Profiles Mode
    profiles = batch_manager.load_profiles()
    if not profiles:
        st.info("No saved profiles found. Run a scan first and save it!")
    else:
        st.sidebar.header("📂 Profiles")
        p_selected = st.sidebar.selectbox("Select Profile", sorted(list(profiles.keys())))
        profile_data = profiles[p_selected]

        st.header(f"📋 Profile: {p_selected}")
        st.caption(f"Students: {len(profile_data.get('regs', []))}")

        # --- Clickable Student List ---
        with st.expander("👥 View Student List"):
            p_regs = profile_data.get('regs', [])
            pro_id_p = profile_data.get('pro_id', '')
            import urllib.parse as _urlparse
            student_links_html = f"""
            <style>
            .stu-list {{ list-style: none; padding: 0; margin: 0; }}
            .stu-list li {{ padding: 8px 12px; border-bottom: 1px solid var(--secondary-background-color); }}
            .stu-list a {{ color: var(--primary-color); text-decoration: none; font-weight: 500; }}
            .stu-list a:hover {{ text-decoration: underline; }}
            </style>
            <ol class="stu-list">
            """
            for r in p_regs:
                reg_no = r[0] if isinstance(r, list) else r
                name   = r[2] if isinstance(r, list) and len(r) > 2 else f"Reg {reg_no}"
                tx_url = f"/transcript?reg={reg_no}&pro_id={_urlparse.quote(str(pro_id_p))}&profile={_urlparse.quote(p_selected)}"
                student_links_html += f"<li><a href='{tx_url}' target='_blank'>📄 {name} <span style='color:var(--text-color);opacity:0.5;font-size:0.85em'>({reg_no})</span></a></li>"
            student_links_html += "</ol>"
            st.markdown(student_links_html, unsafe_allow_html=True)

        # --- Admin Actions ---
        if st.session_state.is_admin:
            with st.expander("⚙️ Admin Actions"):
                col_a, col_b = st.columns(2)
                with col_a:
                    new_name = st.text_input("Rename Profile", value=p_selected)
                    if st.button("📝 Rename") and new_name != p_selected:
                        profiles[new_name] = profiles.pop(p_selected)
                        with open(batch_manager.filename, 'w') as f: json.dump(profiles, f)
                        st.rerun()
                with col_b:
                    st.write("")
                    st.write("")
                    if st.button("🗑️ DELETE PROFILE", type="secondary"):
                        profiles.pop(p_selected)
                        with open(batch_manager.filename, 'w') as f: json.dump(profiles, f)
                        st.rerun()

        # --- Exam Navigation: Centered Bullet Links ---
        exams_raw = fetch_exams(profile_data.get('pro_id')) if profile_data.get('pro_id') else {}
        if not exams_raw:
            st.warning("⚠️ No examinations found for this saved program.")
        else:
            p_regs = profile_data.get('regs', [])
            active_sess_id = profile_data.get('sess_id') or (p_regs[0][1] if p_regs else "Any")
            active_sess_name = SESSIONS_CACHE.get(str(active_sess_id), str(active_sess_id))
            probe_regs = [r[0] for r in p_regs if str(r[1]) == str(active_sess_id)][:5]
            mains_dict, others_dict = classify_exams(
                exams_raw, active_sess_name,
                probe_regs=probe_regs, pro_id=profile_data.get('pro_id')
            )
            mains = [(k, v) for k, v in mains_dict.items()]
            others = [(k, v) for k, v in others_dict.items()]

            import urllib.parse as _urlparse2
            def exam_link(eid, ename, profile):
                url = f"/results?profile={_urlparse2.quote(profile)}&exam_id={eid}&exam_name={_urlparse2.quote(ename)}"
                return f"<li>• <a href='{url}' target='_blank'>{ename}</a></li>"

            css_exam = """
            <style>
            .exam-nav { list-style: none; padding: 0; text-align: center; }
            .exam-nav li { padding: 10px 0; border-bottom: 1px solid var(--secondary-background-color); font-size: 1.05em; }
            .exam-nav a { color: var(--primary-color); text-decoration: none; font-weight: 600; }
            .exam-nav a:hover { text-decoration: underline; opacity: 0.85; }
            .exam-section-label { text-align: center; font-size: 0.8rem; font-weight: 700;
                letter-spacing: 0.1em; opacity: 0.6; margin: 24px 0 8px; text-transform: uppercase; color: var(--text-color); }
            </style>
            """
            st.markdown(css_exam, unsafe_allow_html=True)

            if mains:
                main_links = "".join(exam_link(eid, ename, p_selected) for eid, ename in mains)
                st.markdown(f"""
                <div class='exam-section-label'>⭐ Main Batch Exams</div>
                <ul class='exam-nav'>{main_links}</ul>
                """, unsafe_allow_html=True)

            if others:
                with st.expander("🔄 Other / Retake Exams", expanded=False):
                    other_links = "".join(exam_link(eid, ename, p_selected) for eid, ename in others)
                    st.markdown(f"<ul class='exam-nav'>{other_links}</ul>", unsafe_allow_html=True)

# --- End of Saved Profiles / Interactive Scan Logic ---
# Logic below this was deleted as the dashboard now uses standalone results/transcript pages.

st.markdown("---")
st.caption("Developed with ❤️ for Academic Excellence | Showcase Version")

# Persistent Admin Access at the bottom of the sidebar
with st.sidebar:
    st.write("<div style='margin-top: 50px;'></div>", unsafe_allow_html=True)
    with st.expander("🔒 Admin Access"):
        admin_pw = st.text_input("Admin Password", type="password", key="admin_pw_global")
        st.session_state.is_admin = (admin_pw == "admin123")
        if st.session_state.is_admin:
            st.success("Admin Mode Active")
        elif admin_pw:
            st.error("Invalid Password")

from .network import *
import re
import os
import urllib.parse as urllib_parse
import subprocess
import time
import threading
import sys

def generate_html_report(results, report_title, pro_id=None, sess_id=None):
    """Builds a responsive HTML report optimized for Mobile."""
    
    # Sort results by Registration No
    def get_reg_sort_key(res):
        try: return (0, int(res['Registration No']))
        except Exception: return (1, str(res['Registration No']))
    results.sort(key=get_reg_sort_key)
    
    # Ranking logic
    valid_gpa_results = []
    for res in results:
        try:
            gpa = float(res['GPA'])
            valid_gpa_results.append((gpa, res))
        except (ValueError, TypeError): pass
    valid_gpa_results.sort(key=lambda x: x[0], reverse=True)
    top_half_count = (len(valid_gpa_results) + 1) // 2

    valid_cgpa_results = []
    for res in results:
        try:
            cgpa = float(res['CGPA'])
            valid_cgpa_results.append((cgpa, res))
        except (ValueError, TypeError): pass
    valid_cgpa_results.sort(key=lambda x: x[0], reverse=True)
    css = """
    <style>
        body { 
            font-family: 'Times New Roman', Times, serif; 
            background-color: #fff; color: #000; line-height: 1.5; margin: 0; padding: 20px 10px;
        }
        #cli-report-root .container { max-width: 900px; margin: 0 auto; }
        #cli-report-root .report-block { 
            background: #fff; padding: 25px; border-radius: 0; margin-bottom: 40px;
            border: 1px solid #000;
            display: block;
            box-sizing: border-box;
            page-break-inside: avoid;
        }
        #cli-report-root .title-section { text-align: center; margin-bottom: 25px; border-bottom: 2px solid #000; padding-bottom: 15px; }
        #cli-report-root h1 { color: #000; font-size: 26px; margin: 0 0 5px 0; text-transform: uppercase; letter-spacing: 1px; }
        #cli-report-root h2 { 
            color: #000; font-size: 20px; margin: 20px 0 10px 0; font-weight: bold; 
            border-left: 5px solid #000; padding-left: 12px;
            page-break-after: avoid;
        }
        #cli-report-root .summary-text { font-size: 15px; font-weight: bold; color: #333; }
        #cli-report-root .table-container { overflow-x: visible; margin-top: 15px; page-break-inside: avoid; }
        #cli-report-root table { width: 100%; border-collapse: collapse; font-size: 14px; margin-bottom: 20px; table-layout: auto; }
        #cli-report-root tr { page-break-inside: avoid; }
        #cli-report-root th { background: #f4f4f4; color: #000; font-weight: bold; text-align: center; text-transform: uppercase; font-size: 13px; }
        #cli-report-root th, #cli-report-root td { padding: 8px 10px; text-align: left; border: 1px solid #000; }
        #cli-report-root td.center { text-align: center; }
        #cli-report-root .col-sl { width: 45px; text-align: center; }
        #cli-report-root .col-reg { width: 90px; text-align: center; }
        #cli-report-root .col-res { width: 90px; text-align: center; }
        #cli-report-root .col-gpa, #cli-report-root .col-cgpa { width: 60px; text-align: center; }
        #cli-report-root .data-bold { font-weight: bold; }
        #cli-report-root .award-text { font-weight: bold; font-style: italic; }
    </style>
    """

    import datetime
    timestamp_str = get_bd_time().strftime("%Y-%m-%d %H:%M:%S")

    html = ["<div id='cli-report-root'>", css, "<div class='container'>"]
    
    # --- Data Categorization (Main vs Re-adds) ---
    main_list = []
    readd_list = []
    for r in results:
        s_id_final = r.get('_sess_id', sess_id)
        if sess_id and str(s_id_final) != str(sess_id):
            readd_list.append(r)
        else:
            main_list.append(r)

    def render_results_table(data_list, title_text, is_readd=False):
        if not data_list: return ""
        sec_html = f"<h2>{title_text} ({len(data_list)})</h2>"
        sec_html += "<div class='table-container'><table><thead><tr><th class='col-sl'>Sl</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-res'>Result</th><th class='col-gpa'>SGPA</th><th class='col-cgpa'>CGPA</th></tr></thead><tbody>"
        
        for sl, res in enumerate(data_list, 1):
            reg_val = str(res['Registration No'])
            s_id_final = res.get('_sess_id', sess_id)
            name_display = res['Name']
            
            # Show session tag for re-adds
            reg_display = reg_val
            if is_readd:
                 reg_display = f"{reg_val} <small style='font-size:0.8em;'>[{s_id_final}]</small>"

            if pro_id and sess_id:
                # Removed <a> tag to eliminate underlines for PDF professional look
                name_display = res['Name']
                
            sec_html += "<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold'>{1}</td><td>{2}</td><td class='col-res center'>{3}</td><td class='col-gpa data-bold'>{4}</td><td class='col-cgpa data-bold'>{5}</td></tr>".format(
                sl, reg_display, name_display, res['Overall Result'], res['GPA'], res['CGPA']
            )
        sec_html += "</tbody></table></div>"
        return sec_html

    # Block 1: Results Summary (Categorized)
    html.append("<div class='report-block'><div class='title-section'><h1>Faridpur Engineering College</h1>")
    html.append(f"<h2>{report_title}</h2>")
    html.append(f"<span class='summary-text'>Official Batch Report &nbsp;|&nbsp; Generated: {timestamp_str}</span></div>")
    
    # 1. Main Batch Table (Registration Wise SGPA/CGPA)
    html.append(render_results_table(main_list, "Registration-Wise Result (Regular Batch)"))
    
    # 2. Re-adds Table
    html.append(render_results_table(readd_list, "Registration-Wise Result (Re-adds & Seniors)", is_readd=True))
    
    html.append("</div>") # End block 1
    
    # Block 2: Scholarship Eligibility (Ranked by SGPA)
    if valid_gpa_results:
        html.append("<div class='report-block'><h2>Scholarship Eligibility List (Ranked by SGPA)</h2>")
        html.append("<div class='table-container'><table><thead><tr><th class='col-sl'>Rank</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-gpa'>SGPA</th><th class='col-award'>Status</th></tr></thead><tbody>")
        for sl, item in enumerate(valid_gpa_results, 1):
            res = item[1]
            scholarship = "<span class='award-text'>Eligible</span>" if sl <= top_half_count else ""
            html.append("<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold center'>{1}</td><td>{2}</td><td class='col-gpa data-bold'>{3}</td><td class='col-award center'>{4}</td></tr>".format(
                sl, res['Registration No'], res['Name'], res['GPA'], scholarship
            ))
        html.append("</tbody></table></div></div>")
    
    # Block 3: CGPA Ranking List
    if valid_cgpa_results:
        html.append("<div class='report-block'><h2>Overall Batch CGPA Ranking</h2>")
        html.append("<div class='table-container'><table><thead><tr><th class='col-sl'>Rank</th><th class='col-reg'>Reg No</th><th>Name</th><th class='col-cgpa'>CGPA</th></tr></thead><tbody>")
        for sl, item in enumerate(valid_cgpa_results, 1):
            res = item[1]
            html.append("<tr><td class='col-sl center'>{0}</td><td class='col-reg data-bold center'>{1}</td><td>{2}</td><td class='col-cgpa data-bold'>{3}</td></tr>".format(
                sl, res['Registration No'], res['Name'], res['CGPA']
            ))
        html.append("</tbody></table></div></div>")
    
    html.append("</div></div>")
    return "".join(html)

def generate_transcript_report(records, title, name, return_html=False):
    css = """
    :root { 
        --bg: #111827; --text: #f3f4f6; --card: #1f2937; --border: #374151; 
        --primary: #3b82f6; --accent: #60a5fa; --header: #374151;
    }
    #cli-transcript-root { background-color: var(--bg); color: var(--text); padding: 25px; font-family: 'Outfit', sans-serif; min-height: 100vh; }
    #cli-transcript-root .header-card { background: var(--card); padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 25px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); max-width: 900px; margin-left: auto; margin-right: auto; }
    #cli-transcript-root h2 { margin: 0 0 10px 0; font-size: 1.2em; color: var(--primary); }
    #cli-transcript-root p { margin: 0; font-size: 1em; color: var(--text); opacity: 0.9; }
    #cli-transcript-root .exam-block { background: var(--card); border: 1px solid var(--border); border-left: 5px solid var(--primary); border-radius: 6px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); max-width: 900px; margin-left: auto; margin-right: auto; overflow: hidden; }
    #cli-transcript-root .exam-title { color: var(--accent); padding: 15px 20px; font-weight: 600; font-size: 0.95em; margin: 0; background: var(--header); }
    #cli-transcript-root table { width: 100%; border-collapse: collapse; }
    #cli-transcript-root th, #cli-transcript-root td { padding: 12px 20px; text-align: left; }
    #cli-transcript-root th { background: var(--header); color: var(--text); font-weight: 700; font-size: 0.85em; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); opacity: 0.8; }
    #cli-transcript-root td { border-bottom: 1px solid var(--border); font-size: 0.9em; color: var(--text); }
    #cli-transcript-root .summary { background: var(--header); padding: 12px 20px; font-weight: 600; color: var(--text); font-size: 0.9em; border-top: 1px solid var(--border); border-radius: 0 0 6px 6px; display: flex; gap: 5px;}
    """
    # CSS Prefixing for Dashboard Injection
    css_wrapped = "<div id='cli-transcript-root'><style>" + css + "</style>"
    
    # Header Section
    reg_val = records[0].get('Registration No', '-') if records else '-'
    html = css_wrapped + "<div class='header-card'><h2>&#127775; Student Record</h2><p><b>" + str(name) + "</b> (Reg: " + str(reg_val) + ")</p></div>"

    for r in records:
        html += "<div class='exam-block'>"
        
        exam_name_parsed = r.get('_exam_name', title)
        html += "<div class='exam-title'>&#128197; {}</div>".format(exam_name_parsed)
        
        if r.get('Subjects'):
            html += "<table><thead><tr><th>Code</th><th>Subject</th><th>Grade</th><th>GP</th></tr></thead><tbody>"
            for s in r['Subjects']:
                html += "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(s.get('code','-'), s['name'], s['grade'], s['gp'])
            html += "</tbody></table>"
            
        e_name = r.get('_exam_name', '').lower()
        is_extra = any(x in e_name for x in ["retake", "improvement", "clearance", "special", "junior"])
        
        if not is_extra:
            html += "<div class='summary'>"
            html += "Result: {} | GPA: {} | CGPA: {}".format(r.get('Overall Result', '-'), r.get('GPA', '-'), r.get('CGPA', '-'))
            html += "</div>"
        html += "</div>"
        
    html += "</div>" # Close cli-transcript-root
    if return_html: return html
    
    # Wrap in standard HTML for saving to file
    html_file = f"<html><head><meta charset='utf-8'><title>Student Record - {name}</title></head><body>{html}</body></html>"

    fname = "Student_Record_{}_{}.html".format(name.replace(" ", "_"), get_bd_time().strftime("%H%M%S"))
    downloads_dir = "/storage/emulated/0/Download"
    fpath = os.path.join(downloads_dir if os.path.exists(downloads_dir) else SCRIPT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f: f.write(html_file)
    print("\n✅ Document saved: {}".format(fpath))
    
    try:
        os.chdir(os.path.dirname(fpath))
        import http.server, socketserver
        class SilentH(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        server = socketserver.TCPServer(("0.0.0.0", 0), SilentH)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        # Resilient Viewer using native webbrowser (best for Pydroid 3)
        url = "http://localhost:{}/{}".format(port, urllib_parse.quote(os.path.basename(fpath)))
        print("\n🔗 Web Viewer active at: {}".format(url))
        print("💡 If it doesn't open automatically, you can open it manually from your Downloads folder.")
        
        # Give the server thread a moment to bind
        time.sleep(0.5)
        
        try: 
            import webbrowser
            # On Android, webbrowser.open can sometimes be finicky 
            # if called too soon or with localhost vs 127.0.0.1
            webbrowser.open(url)
        except:
            # Fallback to am start if webbrowser fails
            try:
                with open(os.devnull, 'w') as fnull:
                    subprocess.call(["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-t", "text/html", "-d", url], stdout=fnull, stderr=fnull)
            except: pass
            
        input_func("\nPress Enter to stop viewer...")
        server.shutdown()
        os.chdir(ORIGINAL_DIR)
    except: pass


"""
generate_pdf.py
---------------
Generates a PDF report of all-college CSE 4th Year 1st Semester 2024 results.
Matches the MAIN BRANCH (scraper_core/reports.py) print-ready format exactly,
with one additional "College" column injected into every results table.

No changes are made to the main project files.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

EXAM_TITLE  = "B.Sc. in Computer Science and Engineering 4th Year 1st Semester Examination - 2024"
MAIN_SESS   = '21'   # session that counts as "Regular Batch"

BD_TZ = timezone(timedelta(hours=6))


def get_bd_time():
    return datetime.now(BD_TZ)


def generate_html(results):
    # Sort by Registration No
    results.sort(key=lambda r: (0, int(r['Registration No'])) if str(r['Registration No']).isdigit() else (1, str(r['Registration No'])))

    # Split into regular batch vs re-adds (senior session)
    main_list  = [r for r in results if str(r.get('_sess_id', MAIN_SESS)) == MAIN_SESS]
    readd_list = [r for r in results if str(r.get('_sess_id', MAIN_SESS)) != MAIN_SESS]

    # Scholarship / GPA ranking
    valid_gpa = sorted(
        [(float(r['GPA']), r) for r in results if r.get('GPA', '-') not in ('-', '', None) and str(r['GPA']).replace('.', '').isdigit()],
        key=lambda x: x[0], reverse=True
    )
    top_half = (len(valid_gpa) + 1) // 2

    valid_cgpa = sorted(
        [(float(r['CGPA']), r) for r in results if r.get('CGPA', '-') not in ('-', '', None) and str(r['CGPA']).replace('.', '').isdigit()],
        key=lambda x: x[0], reverse=True
    )

    timestamp_str = get_bd_time().strftime("%Y-%m-%d %H:%M:%S")

    css = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&display=swap');

    * { box-sizing: border-box; margin: 0; padding: 0; }

    @page {
        size: 230mm 5500mm; /* Continuous scroll: massive height */
        margin: 0;
    }

    body {
        font-family: 'Outfit', Arial, sans-serif;
        background: #fff;
        color: #000;
        padding: 40px;
        font-size: 14px;
    }

    #cli-report-root .container { max-width: 960px; margin: 0 auto; }

    #cli-report-root .report-block {
        background: #fff;
        padding: 20px;
        margin-bottom: 30px;
        border: 1px solid #ccc;
    }

    #cli-report-root .title-section {
        text-align: center;
        margin-bottom: 18px;
        border-bottom: 2px solid #000;
        padding-bottom: 12px;
    }

    #cli-report-root .title-section h1 {
        font-size: 18px;
        font-weight: 700;
        color: #000;
        margin-bottom: 4px;
    }

    #cli-report-root .title-section h2 {
        font-size: 14px;
        font-weight: 600;
        color: #000;
        margin-bottom: 4px;
        border: none;
        padding: 0;
    }

    #cli-report-root .summary-text {
        font-size: 13px;
        font-weight: bold;
        color: #333;
    }

    #cli-report-root h2 {
        font-size: 14px;
        font-weight: 700;
        margin: 14px 0 8px 0;
        color: #000;
        border-left: 4px solid #000;
        padding-left: 8px;
    }

    #cli-report-root .table-container {
        overflow-x: visible;
        margin-top: 10px;
    }

    #cli-report-root table {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        margin-bottom: 15px;
        table-layout: auto;
    }

    #cli-report-root th {
        background: #f4f4f4;
        color: #000;
        font-weight: bold;
        text-align: center;
        text-transform: uppercase;
        font-size: 12px;
    }

    #cli-report-root th, #cli-report-root td {
        padding: 8px 10px;
        text-align: left;
        border: 1px solid #000;
    }

    #cli-report-root td.center { text-align: center; }

    #cli-report-root .col-sl  { width: 40px;  text-align: center; }
    #cli-report-root .col-reg { width: 80px;  text-align: center; }
    #cli-report-root .col-res { width: 80px;  text-align: center; }
    #cli-report-root .col-gpa,
    #cli-report-root .col-cgpa { width: 55px; text-align: center; }
    #cli-report-root .col-college { width: 180px; }

    #cli-report-root .data-bold { font-weight: bold; }
    #cli-report-root .award-text { font-weight: bold; font-style: italic; }

    @media print {
        body { padding: 40px; }
        #cli-report-root .report-block { border: 1px solid #999; }
    }
    </style>
    """

    def render_table(data_list, title_text, is_readd=False):
        if not data_list:
            return ""
        html = f"<h2>{title_text} ({len(data_list)})</h2>"
        html += """<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Sl</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-res'>Result</th>
            <th class='col-gpa'>SGPA</th>
            <th class='col-cgpa'>CGPA</th>
        </tr></thead><tbody>"""

        for sl, res in enumerate(data_list, 1):
            reg_val = str(res['Registration No'])
            sess_tag = ""
            if is_readd:
                sess_tag = f" <small style='font-size:0.8em;'>[{res.get('_sess_id', '?')}]</small>"
            college = res.get('College', '-')
            html += (
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold'>{reg_val}{sess_tag}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{college}</td>"
                f"<td class='col-res center'>{res['Overall Result']}</td>"
                f"<td class='col-gpa data-bold center'>{res['GPA']}</td>"
                f"<td class='col-cgpa data-bold center'>{res['CGPA']}</td>"
                f"</tr>"
            )

        html += "</tbody></table></div>"
        return html

    parts = [f"<div id='cli-report-root'>{css}<div class='container'>"]

    # Block 1: Results
    parts.append("<div class='report-block'>")
    parts.append(f"""
        <div class='title-section'>
            <h1>All Affiliated Colleges &amp; Institutes</h1>
            <h2>{EXAM_TITLE}</h2>
            <span class='summary-text'>
                All-College Result Report | Total Students Found: {len(results)}
                | Generated: {timestamp_str}
            </span>
        </div>
    """)
    parts.append(render_table(main_list,  "Registration-Wise Result (Regular Batch - Session 2021-22)"))
    parts.append(render_table(readd_list, "Registration-Wise Result (Re-adds / Senior Batches)", is_readd=True))
    parts.append("</div>")  # end block 1

    # Block 2: Scholarship eligibility (ranked by SGPA)
    if valid_gpa:
        parts.append("<div class='report-block'><h2>Scholarship Eligibility List (Ranked by SGPA)</h2>")
        parts.append("""<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Rank</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-gpa'>SGPA</th>
            <th class='col-award'>Status</th>
        </tr></thead><tbody>""")
        for sl, (gpa_val, res) in enumerate(valid_gpa, 1):
            eligible = "<span class='award-text'>Eligible</span>" if sl <= top_half else ""
            parts.append(
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold center'>{res['Registration No']}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{res.get('College', '-')}</td>"
                f"<td class='col-gpa data-bold center'>{res['GPA']}</td>"
                f"<td class='center'>{eligible}</td>"
                f"</tr>"
            )
        parts.append("</tbody></table></div></div>")

    # Block 3: CGPA ranking
    if valid_cgpa:
        parts.append("<div class='report-block'><h2>Overall Batch CGPA Ranking</h2>")
        parts.append("""<div class='table-container'><table><thead><tr>
            <th class='col-sl'>Rank</th>
            <th class='col-reg'>Reg No</th>
            <th>Name</th>
            <th class='col-college'>College / Institute</th>
            <th class='col-cgpa'>CGPA</th>
        </tr></thead><tbody>""")
        for sl, (cgpa_val, res) in enumerate(valid_cgpa, 1):
            parts.append(
                f"<tr>"
                f"<td class='col-sl center'>{sl}</td>"
                f"<td class='col-reg data-bold center'>{res['Registration No']}</td>"
                f"<td>{res['Name']}</td>"
                f"<td class='col-college'>{res.get('College', '-')}</td>"
                f"<td class='col-cgpa data-bold center'>{res['CGPA']}</td>"
                f"</tr>"
            )
        parts.append("</tbody></table></div></div>")

    parts.append("</div></div>")
    return "".join(parts)


def find_edge():
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(p):
            return p
    return None


def main():
    results_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'found_results.json')
    if not os.path.exists(results_file):
        print("ERROR: found_results.json not found. Run find_results_proxy.py first.")
        sys.exit(1)

    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)

    if not results:
        print("ERROR: found_results.json is empty.")
        sys.exit(1)

    print(f"Loaded {len(results)} student records.")

    html_content = generate_html(results)

    # Wrap in proper standalone HTML doc
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CSE 4th Year 1st Semester 2024 - All Colleges Result</title>
</head>
<body>
{html_content}
</body>
</html>"""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "results_report.html")
    pdf_path  = os.path.join(base_dir, "4th_year_1st_sem_2024_results.pdf")

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"HTML written to {html_path}")

    edge = find_edge()
    if not edge:
        print("Microsoft Edge not found. Please open results_report.html manually and print to PDF.")
        return

    html_url = "file:///" + html_path.replace("\\", "/")
    cmd = [
        edge,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        "--no-pdf-header-footer",
        html_url,
    ]
    print("Rendering PDF via Edge headless...")
    subprocess.run(cmd, check=False)

    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
        print(f"PDF saved to {pdf_path}")
    else:
        print("PDF generation may have failed. Check results_report.html manually.")


if __name__ == '__main__':
    main()


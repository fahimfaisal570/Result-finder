import streamlit as st

def inject_essential_ui():
    """
    Injects essential UI fixes while rolling back the "Midnight Glass" styling.
    Features:
    - Responsive column stacking for mobile screens (< 768px).
    - Hiding the 'Fork' button and default Streamlit footer.
    - Keeping the dark/light mode toggle (MainMenu) visible.
    """
    minimal_css = """
    <style>
        /* Import Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Inter:wght@400;500;600&family=Outfit:wght@500;600;700&display=swap');

        /* Base Typography */
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif !important;
        }

        /* Headings (Outfit) */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
        }
        
        h1 { font-weight: 700 !important; }

        /* Monospace / Data (Fira Code) */
        code, pre, .st-key-reg_no, [data-testid="stMetricValue"] {
            font-family: 'Fira Code', monospace !important;
        }

        /* [MAINTENANCE] Hide Streamlit Branding and Menus */
        [data-testid="stHeader"] a { display: none !important; }
        #MainMenu { visibility: hidden !important; }
        footer { visibility: hidden !important; height: 0 !important; }
        
        /* [MAINTENANCE] Mobile Support: Column Stacking */
        @media screen and (max-width: 768px) {
            [data-testid="column"] {
                width: 100% !important;
                flex-basis: 100% !important;
                margin-bottom: 1rem !important;
            }
            .stMetric { margin-bottom: 20px !important; }
        }

        /* [MAINTENANCE] Sidebar Streamlining */
        [data-testid="stSidebarNav"] { display: none !important; }

        /* Premium Component Styling */
        
        /* Metrics */
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 16px !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            transition: transform 0.2s ease;
        }
        [data-testid="stMetric"]:hover {
            transform: translateY(-2px);
        }
        [data-testid="stMetricLabel"] {
            font-weight: 500 !important;
            opacity: 0.8;
            font-family: 'Inter', sans-serif !important;
            text-transform: uppercase;
            font-size: 0.75rem !important;
            letter-spacing: 0.05em;
        }
        
        /* Expanders */
        [data-testid="stExpander"] {
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 8px !important;
            background: rgba(255, 255, 255, 0.02) !important;
        }
        [data-testid="stExpander"] summary {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 500 !important;
        }

        /* Inline Markdown Content (Course Listings, GP Labels) */
        [data-testid="stExpander"] p,
        [data-testid="stVerticalBlock"] p {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.92rem !important;
            line-height: 1.65 !important;
            letter-spacing: 0.01em;
        }
        
        /* Inline Code Tags (Course Codes like CE-601) */
        [data-testid="stExpander"] code,
        [data-testid="stVerticalBlock"] code {
            font-family: 'Fira Code', monospace !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            background: rgba(99, 102, 241, 0.12) !important;
            color: rgba(165, 180, 252, 1) !important;
            padding: 2px 7px !important;
            border-radius: 5px !important;
            border: 1px solid rgba(99, 102, 241, 0.15) !important;
            letter-spacing: 0.03em;
        }

        /* Strong/Bold inside markdown (Course Names) */
        [data-testid="stExpander"] strong {
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
        }

        /* Italic inside markdown (Subject Full Names) */
        [data-testid="stExpander"] em {
            font-family: 'Inter', sans-serif !important;
            font-style: italic;
            opacity: 0.85;
        }

        /* Number Inputs (GP Target Spinners) */
        [data-testid="stNumberInput"] input {
            font-family: 'Fira Code', monospace !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            letter-spacing: 0.02em;
        }

        /* Bordered Containers (Student Cards) */
        [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 10px !important;
            transition: border-color 0.2s ease;
        }

        /* Captions */
        [data-testid="stCaptionContainer"] {
            font-family: 'Inter', sans-serif !important;
            font-size: 0.78rem !important;
            letter-spacing: 0.02em;
            opacity: 0.65;
        }

        /* Slider Labels */
        [data-testid="stSlider"] label {
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
        }
        [data-testid="stSlider"] [data-testid="stThumbValue"] {
            font-family: 'Fira Code', monospace !important;
        }

        /* Text Inputs (Search Bar) */
        [data-testid="stTextInput"] label {
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
        }
        [data-testid="stTextInput"] input {
            font-family: 'Inter', sans-serif !important;
        }

        /* Dividers */
        [data-testid="stMarkdownContainer"] hr {
            border-color: rgba(255, 255, 255, 0.06) !important;
            margin: 1.5rem 0 !important;
        }

        /* Tabs */
        [data-testid="stTabs"] button {
            font-family: 'Outfit', sans-serif !important;
            font-weight: 500 !important;
        }

        /* Links */
        a { 
            color: inherit !important; 
            text-decoration: none !important; 
            font-weight: 500 !important; 
            transition: opacity 0.2s ease;
        }
        a:hover { 
            text-decoration: underline !important; 
            opacity: 0.8;
        }
        
        /* Buttons */
        [data-testid="baseButton-secondary"] {
            font-family: 'Inter', sans-serif !important;
            font-weight: 500 !important;
            border-radius: 8px !important;
        }
        [data-testid="baseButton-primary"] {
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
            border-radius: 8px !important;
            background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
            border: none !important;
            box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3) !important;
        }
        [data-testid="baseButton-primary"]:hover {
            box-shadow: 0 6px 8px -1px rgba(37, 99, 235, 0.4) !important;
            transform: translateY(-1px);
        }
    </style>
    """
    st.markdown(minimal_css, unsafe_allow_html=True)

    # JavaScript for Hover-to-Open selectboxes (maintained from original)
    hover_js = """
    <script>
        (function() {
            const doc = (window.parent && window.parent.document) ? window.parent.document : document;
            const trigger = (el) => {
                ['mousedown', 'mouseup', 'click'].forEach(name => {
                    const evt = new MouseEvent(name, { bubbles: true, cancelable: true, view: window.parent || window });
                    el.dispatchEvent(evt);
                });
            };

            const handleHover = (e) => {
                const selectbox = e.target.closest('div[data-testid="stSelectbox"]');
                if (selectbox && !selectbox.dataset.hoverLock) {
                     const btn = selectbox.querySelector('div[role="button"]') || selectbox.querySelector('input');
                     const isOpen = !!doc.querySelector('div[role="listbox"]');
                     
                     if (btn && !isOpen) {
                         trigger(btn);
                         selectbox.dataset.hoverLock = "true";
                         setTimeout(() => { selectbox.dataset.hoverLock = ""; }, 500);
                     }
                }
            };

            doc.addEventListener('mouseover', handleHover);
        })();
    </script>
    """
    st.markdown(hover_js, unsafe_allow_html=True)

def add_contact_section():
    """
    Adds a stylized social contact footer (LinkedIn & Facebook).
    """
    contact_html = """
    <style>
    .premium-footer {
        margin-top: 4rem;
        padding: 2rem 1rem;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1.5rem;
        animation: fadeIn 0.8s ease forwards;
    }
    .footer-socials {
        display: flex;
        gap: 1rem;
    }
    .social-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.7) !important;
        transition: all 0.2s ease;
    }
    .social-btn:hover {
        background: rgba(255, 255, 255, 0.1);
        color: white !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    .social-btn svg {
        width: 20px;
        height: 20px;
        fill: currentColor;
    }
    .footer-text {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        color: rgba(255, 255, 255, 0.5);
        letter-spacing: 0.02em;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    </style>
    <div class="premium-footer">
        <div class="footer-socials">
            <a href="https://www.linkedin.com/in/fahimfaisal09" target="_blank" class="social-btn" title="LinkedIn">
                <svg viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
            </a>
            <a href="https://www.facebook.com/share/17EJzb4i2E/" target="_blank" class="social-btn" title="Facebook">
                <svg viewBox="0 0 24 24"><path d="M9 8h-3v4h3v12h5v-12h3.642l.358-4h-4v-1.667c0-.955.192-1.333 1.115-1.333h2.885v-5h-3.808c-3.596 0-5.192 1.583-5.192 4.615v3.385z"/></svg>
            </a>
        </div>
        <div class="footer-text">
            Developed for Academic Excellence
        </div>
    </div>
    """
    st.markdown(contact_html, unsafe_allow_html=True)

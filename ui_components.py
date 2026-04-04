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
        /* [MAINTENANCE] Hide Streamlit Branding */
        [data-testid="stHeader"] a { display: none !important; }
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

        /* [RESTORED] Showcase Typography (Bold & Neutral Links) */
        a { 
            color: inherit !important; 
            text-decoration: none !important; 
            font-weight: bold !important; 
        }
        a:hover { 
            text-decoration: underline !important; 
            opacity: 0.8;
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
    Adds a stylized social contact footer (preserved from revamp).
    """
    contact_html = f"""
    <div style="margin-top: 5rem; padding: 2rem 1rem; border-top: 1px solid rgba(255, 255, 255, 0.05); text-align: center;">
        <div style="display: flex; justify-content: center; gap: 25px; align-items: center; opacity: 0.7;">
            <a href="https://www.linkedin.com/in/fahimfaisal09" target="_blank">
                <img src="https://img.icons8.com/color/48/000000/linkedin.png" width="28" height="28">
            </a>
            <a href="https://www.facebook.com/share/17EJzb4i2E/" target="_blank">
                <img src="https://img.icons8.com/color/48/000000/facebook-new.png" width="28" height="28">
            </a>
            <a href="https://github.com/fahimfaisal570/Result-finder" target="_blank">
                <img src="https://img.icons8.com/ios-filled/50/ffffff/github.png" width="28" height="28" style="filter: brightness(0.8);">
            </a>
        </div>
    </div>
    """
    st.markdown(contact_html, unsafe_allow_html=True)

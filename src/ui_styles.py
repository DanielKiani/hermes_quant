def get_custom_css():
    return """
    <style>
        /* Make header transparent */
        header[data-testid="stHeader"] { background: transparent !important; }
        
        /* Hide the right-side toolbar for a clean look */
        div[data-testid="stToolbar"] { display: none !important; }

        /* Reduce block padding so our custom sticky nav touches the top */
        .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; max-width: 98% !important; }
        
        /* Sticky Top Navigation Hack */
        div.element-container:has(#sticky-nav) { display: none; }
        div.element-container:has(#sticky-nav) + div.element-container {
            position: sticky; top: 0; z-index: 1000; background-color: #0b0e11;
            padding-top: 1rem; padding-bottom: 0.5rem; margin-top: -1rem; border-bottom: 1px solid #222531;
        }
        
        /* Top Navigation Radio Buttons (Make them look like tabs) */
        div[role="radiogroup"] { gap: 1rem !important; justify-content: flex-end; }
        div[role="radiogroup"] > label { background: transparent !important; border: none !important; padding: 0 !important; }
        div[role="radiogroup"] > label > div:first-child { display: none !important; }
        div[role="radiogroup"] > label > div:last-child { font-weight: 600; font-size: 14px; color: #8A919E; margin: 0; }
        div[role="radiogroup"] > label[data-checked="true"] > div:last-child { color: #F3F5F7 !important; border-bottom: 2px solid #0052FF; padding-bottom: 4px; }
        
        /* Native Scrollbar Styling */
        div[data-testid="stVerticalBlock"] > div > div > div > div > div { scrollbar-width: thin; scrollbar-color: #222531 transparent; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #222531; border-radius: 4px; }
        
        /* Portfolio Items Styling */
        .portfolio-item {
            background-color: #171924; border: 1px solid #222531; border-radius: 8px;
            padding: 16px; margin-bottom: 12px; display: flex; justify-content: space-between;
            align-items: center; transition: border-color 0.2s;
        }
        .portfolio-item:hover { border-color: #0052FF; }
        
        /* Static Left Header */
        .left-static-header {
            background-color: #171924; padding: 16px; margin-bottom: 15px;
            border: 1px solid #222531; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.2);
        }
        
        /* Small Grid Info Boxes */
        .small-info-box { background-color: #171924; border: 1px solid #222531; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; justify-content: center; }
        .small-info-label { color: #8A919E; font-size: 11px; margin-bottom: 4px; display: flex; align-items: center; }
        .small-info-val { color: #F3F5F7; font-size: 13px; font-weight: 600; }
        
        /* Price Performance Bar */
        .perf-bar-bg { height: 4px; background-color: #2B2C33; border-radius: 2px; position: relative; margin-top: 8px; margin-bottom: 8px; }
        .perf-dot { position: absolute; top: -3px; width: 10px; height: 10px; background-color: #F3F5F7; border-radius: 50%; box-shadow: 0 0 4px rgba(0,0,0,0.5); }
        
        /* Market Movers section */
        .movers-header { font-size: 14px; font-weight: 700; color: #F3F5F7; margin-top: 15px; margin-bottom: 10px; padding-bottom: 4px; border-bottom: 1px solid #222531; }
        
        /* Vibrant Links & News */
        .news-link { color: #F3F5F7; text-decoration: none; font-weight: 600; font-size: 13px; line-height: 1.4; display: block; margin-bottom: 4px; }
        .news-link:hover { color: #0052FF; text-decoration: none; }
        .news-meta { color: #8A919E; font-size: 11px; margin-top: 2px; margin-bottom: 0; }
        
        /* Search Bar Pill Design */
        div[data-testid="stTextInput"] input { background-color: #171924; border: 1px solid #222531; border-radius: 20px; padding-left: 15px; color: #F3F5F7; height: 38px; }
        div[data-testid="stTextInput"] input:focus { border-color: #0052FF; box-shadow: none; }
        
        /* Vertical Column Divider Hack */
        .vertical-line { position: absolute; left: -1rem; top: 0; width: 1px; height: 100%; min-height: 850px; background-color: #222531; z-index: 0; }
        
        /* Streamlit overrides for containers */
        div[data-testid="stVerticalBlock"] > div[style*="border"] { background-color: #171924; border-color: #222531 !important; border-radius: 12px; }
        hr { border-color: #222531 !important; }
        
        /* Primary AI Button */
        .stButton button[kind="primary"] { background-color: #0052FF !important; border: none !important; color: white !important; font-weight: bold; width: 100%; }
        .stButton button[kind="primary"]:hover { background-color: #0045D8 !important; }
        
        /* Tertiary Clickable Links (Tickers) */
        .stButton button[kind="tertiary"] { padding: 0 !important; font-weight: 700 !important; color: #F3F5F7 !important; background: transparent !important; border: none !important; justify-content: flex-start !important; height: auto !important; min-height: 0 !important; line-height: 1.2 !important;}
        .stButton button[kind="tertiary"]:hover { color: #0052FF !important; background: transparent !important; }
        
        /* Universal Button Width Fix to replace use_container_width */
        .full-width-btn button { width: 100% !important; }
    </style>
    """
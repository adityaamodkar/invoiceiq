"""
InvoiceIQ visual system, modelled on working AP platforms: sidebar navigation with counts,
white (or dark) work surfaces, dense tables, soft status badges, one primary action.

Every colour is a CSS variable; dark mode redefines the variables and restyles Streamlit's
own widgets to match. Hanken Grotesk (SIL OFL) is bundled in static/fonts.
"""
import streamlit as st

LIGHT = """
:root {
  --bg:#FFFFFF; --side:#F7F7F5; --surface:#FFFFFF; --subtle:#FAFAF9; --hover:#EFEFEC; --current:#E8E8E4;
  --line:#E7E7E4; --line2:#F1F1EF; --strong:#D3D3CF; --ink:#18181B; --muted:#6B6B72; --faint:#9A9AA0;
  --brand:#3149C9; --brand-wash:#EEF1FD; --primary:#18181B; --on-primary:#FFFFFF; --primary-hover:#2E2E33;
  --ready-bg:#EAF0FF; --ready:#2C45B8; --review-bg:#FFF3DC; --review:#8A5300; --blocked-bg:#FDECEC; --blocked:#B42318;
  --approved-bg:#E6F4EC; --approved:#17703F; --grey-bg:#F1F1EF; --grey:#55555B;
  --a-blocked-bg:#FFF8F7; --a-blocked-bd:#F3C3BF; --a-review-bg:#FFFBF2; --a-review-bd:#F0D9AE;
  --a-ready-bg:#F6F8FF; --a-ready-bd:#D5DDFB; --a-approved-bg:#F3FAF6; --a-approved-bd:#C5E5D2;
  --cell-warn:#FFF7E6; --cell-fail:#FDEEEE; --ok:#2F9E63; --amber:#D08A00; --bar:#3149C9; --bar-before:#A9B3C4;
  --shadow:0 1px 1px rgba(0,0,0,.03); --scrim:rgba(24,24,27,.35);
}
"""

DARK = """
:root {
  --bg:#111113; --side:#17171A; --surface:#1B1B1F; --subtle:#1F1F23; --hover:#24242A; --current:#2A2A31;
  --line:#2C2C32; --line2:#232328; --strong:#3A3A42; --ink:#ECECEF; --muted:#A3A3AD; --faint:#74747E;
  --brand:#8A9BFF; --brand-wash:#1E2340; --primary:#ECECEF; --on-primary:#111113; --primary-hover:#FFFFFF;
  --ready-bg:rgba(110,135,255,.16); --ready:#A9B8FF; --review-bg:rgba(230,160,40,.16); --review:#F2BE5C;
  --blocked-bg:rgba(240,90,80,.16); --blocked:#FF8E85; --approved-bg:rgba(60,180,110,.16); --approved:#73D39F;
  --grey-bg:#26262B; --grey:#B4B4BC;
  --a-blocked-bg:rgba(240,90,80,.08); --a-blocked-bd:rgba(240,90,80,.35); --a-review-bg:rgba(230,160,40,.08);
  --a-review-bd:rgba(230,160,40,.35); --a-ready-bg:rgba(110,135,255,.08); --a-ready-bd:rgba(110,135,255,.35);
  --a-approved-bg:rgba(60,180,110,.08); --a-approved-bd:rgba(60,180,110,.35);
  --cell-warn:rgba(230,160,40,.14); --cell-fail:rgba(240,90,80,.14); --ok:#4CC285; --amber:#E9A93A; --bar:#7C8FFF;
  --bar-before:#5A6072; --shadow:none; --scrim:rgba(0,0,0,.6);
}
/* Streamlit widgets in dark mode */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--bg) !important; }
.stApp, [data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"] p, label, [data-testid="stCaptionContainer"],
  .stCheckbox p, [data-testid="stToggle"] p, details summary, details summary p, [data-testid="stExpander"] p { color: var(--ink); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
  input, textarea { background: var(--surface) !important; color: var(--ink) !important; border-color: var(--line) !important; }
input::placeholder, textarea::placeholder { color: var(--faint) !important; }
[data-baseweb="select"] svg, [data-testid="stExpander"] svg { fill: var(--muted); color: var(--muted); }
[data-baseweb="popover"] > div, [data-baseweb="menu"], [role="listbox"], [data-testid="stPopoverBody"], ul[role="listbox"] li {
  background: var(--surface) !important; color: var(--ink) !important; }
[role="listbox"] li:hover, [role="option"][aria-selected="true"] { background: var(--hover) !important; }
[role="option"], [role="option"] *, [data-baseweb="popover"] li, [data-baseweb="popover"] li * { color: var(--ink) !important; }
[data-baseweb="select"] div { background-color: transparent !important; }
[data-baseweb="select"] > div { background-color: var(--surface) !important; }
[data-baseweb="select"] * { color: var(--ink); }
[data-baseweb="textarea"], [data-baseweb="input"] { border: 1px solid var(--line) !important; }
[data-baseweb="textarea"] textarea, [data-baseweb="input"] input { border: none !important; }
[role="dialog"] button[aria-label="Close"] svg, [role="dialog"] [data-testid="stBaseButton-borderlessIcon"] svg { color: var(--ink) !important; fill: var(--ink) !important; }
[role="dialog"] { background: var(--surface) !important; color: var(--ink); }
[data-testid="stExpander"] details, [data-testid="stExpander"] summary { background: var(--surface) !important; }
[data-testid="stFileUploaderDropzone"] *, [data-testid="stFileUploaderFile"] * { color: var(--muted); }
[data-testid="stFileUploaderDropzone"] button { background: var(--hover) !important; color: var(--ink) !important; border-color: var(--line) !important; }
[data-testid="stButtonGroup"] button, div[data-testid="stSegmentedControl"] button { background: var(--surface) !important; color: var(--muted) !important; border-color: var(--line) !important; }
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[kind*="Active"] { background: var(--current) !important; color: var(--ink) !important; }
[data-testid="stToast"] { background: var(--surface) !important; color: var(--ink) !important; }
[data-testid="stProgress"] > div > div { background: var(--line) !important; }
[data-testid="stAlertContainer"] { background: var(--a-review-bg) !important; color: var(--ink) !important; }
[data-testid="stIconMaterial"] { color: var(--muted); }
[data-testid="stCheckbox"] label:has(input:not([role="switch"]):not(:checked)) > div:first-of-type {
  background: var(--surface) !important; border-color: var(--strong) !important; }
"""

BASE = """
@font-face { font-family:'Hanken Grotesk'; src:url('/app/static/fonts/HankenGrotesk.ttf') format('truetype');
  font-weight:100 900; font-display:swap; }
:root { --font:'Hanken Grotesk', -apple-system, 'Segoe UI', system-ui, sans-serif; }
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded):not([class*="material"]) {
  font-family: var(--font) !important; }
/* dialogs, menus, dropdown lists and toasts are drawn outside .stApp, so they need the font (and a scrim) too */
[data-testid="stDialog"] *:not([data-testid="stIconMaterial"]), [data-testid="stPopoverBody"] *:not([data-testid="stIconMaterial"]),
  [role="listbox"] *, [data-testid="stToast"] *:not([data-testid="stIconMaterial"]), [data-testid="stTooltipContent"] * { font-family: var(--font) !important; }
[data-testid="stDialog"] { background: var(--scrim) !important; }
[data-testid="stDialog"] > div { background: var(--surface) !important; }
[data-testid="stDialog"] [role="dialog"] { background: var(--surface) !important; color: var(--ink); border: 1px solid var(--line); }
.stApp { background: var(--bg); color: var(--ink); }
/* Streamlit's top bar holds the control that reopens a collapsed sidebar, so the bar itself must stay in the
   page. It is made transparent and click-through; only the pieces we don't want inside it are hidden. */
[data-testid="stHeader"] { background: transparent !important; pointer-events: none; }
[data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
  [data-testid="stToolbarActions"], [data-testid="stHeaderLogo"] { display:none !important; }
.stApp:has([data-testid="stExpandSidebarButton"]) .block-container { padding-left: 3.6rem; }
[data-testid="stExpandSidebarButton"] { pointer-events: auto; position: fixed; top: 3.05rem; left: .9rem; z-index: 999991;
  width: 1.75rem; height: 1.75rem; border: 1px solid var(--line) !important; border-radius: 7px; background: var(--surface) !important;
  box-shadow: var(--shadow); display: inline-flex; align-items: center; justify-content: center; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button { color: var(--muted) !important; }
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapseButton"] button * { color: inherit !important; }
[data-testid="stExpandSidebarButton"]:hover, [data-testid="stSidebarCollapseButton"] button:hover { background: var(--hover) !important; color: var(--ink) !important; }
[data-testid="stSidebarCollapseButton"] { visibility: visible !important; opacity: 1 !important; margin: 0 !important; }
[data-testid="stSidebarCollapseButton"] button { width: 1.75rem; height: 1.75rem; border-radius: 7px; }
.block-container { padding: 2rem 2.4rem 4rem; max-width: 1320px; }
h1 { font-size: 1.6rem !important; font-weight: 650 !important; letter-spacing: -0.01em; padding: 0 !important; margin: 0 !important; color: var(--ink); }
h3 { font-size: 1.02rem !important; font-weight: 650 !important; margin: 0 0 .6rem !important; padding: 0 !important; color: var(--ink); }
.num { font-variant-numeric: tabular-nums; } .muted { color: var(--muted); } .small { font-size: .82rem; }

/* ---------- sidebar ---------- */
/* One grid: boxes (button, row highlight, divider) start at --sb-box; everything you read (logo, icons, group
   labels, company, toggle) starts at --sb-box + --sb-pad. The fixed width applies only while the sidebar is open;
   a collapsed sidebar must be free to shrink to nothing. */
[data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--line); --sb-box: .75rem; --sb-pad: .6rem; }
[data-testid="stSidebar"]:has([data-testid="stSidebarCollapseButton"]) { min-width: 17.5rem !important; max-width: 17.5rem !important; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[data-testid="stSidebarContent"] { padding: 0 !important; }
[data-testid="stSidebarHeader"] { padding: 1.1rem var(--sb-box) .5rem calc(var(--sb-box) + var(--sb-pad)) !important; margin: 0 !important;
  height: auto !important; display: flex; align-items: center; justify-content: space-between; }
[data-testid="stSidebarHeader"] img { height: 1.75rem !important; max-width: none; margin: 0 !important; display: block; }
[data-testid="stSidebarUserContent"] { padding: .5rem var(--sb-box) 1rem !important; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .12rem !important; }
[data-testid="stSidebar"] [data-testid="stElementContainer"] { margin: 0 !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] { margin: 0 !important; padding: 0 !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a { padding: .42rem var(--sb-pad) !important; border-radius: 7px; min-height: 0 !important;
  margin: 0 !important; display: flex !important; align-items: center; gap: .6rem; width: 100%; line-height: 1.35; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a:hover { background: var(--hover); }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] { background: var(--current); }
[data-testid="stSidebar"] [data-testid="stPageLink"] p { font-size: .95rem !important; font-weight: 500; color: var(--ink) !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] p { font-weight: 650; }
[data-testid="stSidebar"] [data-testid="stPageLink"] [data-testid="stIconMaterial"] { font-size: 1.15rem; color: var(--muted); }
[data-testid="stSidebar"] [data-testid="stElementContainer"][class*="st-key-nav_upload"] { margin-bottom: .75rem !important; }
[data-testid="stSidebar"] [class*="st-key-nav_home"], [data-testid="stSidebar"] [class*="st-key-nav_invoices"] { gap: 0 !important; margin: 0 !important; }
[data-testid="stSidebar"] [class*="st-key-dark_mode"] { margin: .7rem 0 0 var(--sb-pad) !important; }
/* switches: the off knob was the same colour as the sidebar and disappeared */
[data-testid="stCheckbox"] label:has(input[role="switch"]:not(:checked)) > div:first-of-type { background: var(--strong) !important; }
[data-testid="stCheckbox"] label:has(input[role="switch"]) > div:first-of-type > div { background: #FFFFFF !important;
  box-shadow: 0 1px 2px rgba(0,0,0,.18); }
[data-testid="stSidebar"] [class*="st-key-dark_mode"] p { font-size: .86rem; color: var(--muted) !important; }
[class*="st-key-nav_upload"] button { min-height: 2.4rem; font-size: .93rem; }
.side-group { font-size: .75rem; color: var(--faint); padding: 1.1rem var(--sb-pad) .35rem; font-weight: 600; letter-spacing: .01em; line-height: 1.2; }
.entity { border-top: 1px solid var(--line); margin-top: 1.4rem; padding: .95rem var(--sb-pad) 0; font-size: .82rem; color: var(--muted); line-height: 1.45; }
.entity .cap { font-size: .75rem; color: var(--faint); font-weight: 600; margin-bottom: .25rem; line-height: 1.2; }
.entity b { color: var(--ink); font-weight: 600; display: block; font-size: .9rem; }
.entity span { display: block; font-variant-numeric: tabular-nums; white-space: nowrap; }

/* ---------- buttons, inputs ---------- */
.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button, [data-testid="stPopover"] button {
  border-radius: 7px; font-weight: 600; font-size: .88rem; border: 1px solid var(--line); background: var(--surface);
  color: var(--ink); min-height: 2.2rem; padding: .3rem .9rem; box-shadow: var(--shadow); }
.stButton button:hover, [data-testid="stPopover"] button:hover { border-color: var(--strong); background: var(--subtle); color: var(--ink); }
.stButton button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
  background: var(--primary); border-color: var(--primary); color: var(--on-primary); }
.stButton button[kind="primary"] p, [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] p { color: var(--on-primary) !important; }
.stButton button[kind="primary"]:hover { background: var(--primary-hover); color: var(--on-primary); }
.stButton button[kind="primary"] [data-testid="stIconMaterial"] { color: var(--on-primary) !important; }
.stButton button [data-testid="stIconMaterial"] { color: inherit; }
.stButton button:disabled { opacity: .45; }
[class*="st-key-danger"] button, [class*="st-key-danger"] button p { color: var(--blocked) !important; }
[class*="st-key-confirm_delete"] button, [class*="st-key-confirm_reject"] button { background: #B42318 !important; border-color: #B42318 !important; }
[class*="st-key-confirm_delete"] button p, [class*="st-key-confirm_reject"] button p { color: #fff !important; }
[class*="st-key-approve"] button { background: #17703F !important; border-color: #17703F !important; }
[class*="st-key-approve"] button p { color: #fff !important; }
[data-testid="stFileUploaderDropzone"] { background: var(--subtle); border: 1.5px dashed var(--strong); border-radius: 10px; padding: 1.6rem; }
.stTabs [data-baseweb="tab-list"] { gap: 1.4rem; border-bottom: 1px solid var(--line); background: transparent; }
.stTabs [data-baseweb="tab"] { padding: .55rem 0; background: transparent; }
.stTabs [data-baseweb="tab"] p { font-weight: 600; font-size: .9rem; color: var(--muted); }
.stTabs [aria-selected="true"] p { color: var(--ink); }
[data-baseweb="tab-highlight"] { background: var(--ink) !important; }
[data-baseweb="tab-border"] { background: transparent !important; }
[data-testid="stExpander"] details { border: 1px solid var(--line) !important; border-radius: 8px; }

/* keyboard focus is always visible */
.stApp button:focus-visible, .stApp a:focus-visible, .stApp summary:focus-visible, .stApp [role="tab"]:focus-visible,
  .stApp label:has(input:focus-visible) { outline: 2px solid var(--brand) !important; outline-offset: 2px; border-radius: 7px; box-shadow: none !important; }
/* text boxes and dropdowns: one look in both modes (white or dark surface, hairline border, brand border on focus) */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stSelectbox"] [role="group"] {
  background: var(--surface) !important; border: 1px solid var(--line) !important; border-radius: 7px !important; box-shadow: none !important; }
[data-testid="stTextInputRootElement"] input, [data-testid="stTextAreaRootElement"] textarea, [data-testid="stSelectbox"] [role="group"] input {
  background: transparent !important; color: var(--ink) !important; border: none !important; }
[data-testid="stSelectbox"] [role="group"] button, [data-testid="stSelectbox"] [role="group"] svg { color: var(--muted) !important; fill: currentColor; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within, [data-testid="stSelectbox"] [role="group"]:focus-within,
  [data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--brand) !important; box-shadow: 0 0 0 1px var(--brand) !important; }
.tbl.nwcols th + th, .tbl.nwcols td + td { white-space: nowrap; }

/* ---------- page header ---------- */
/* Streamlit pulls every markdown block 1rem up into the next element (meant for paragraphs). Under a page title
   that glued the content to the heading, so the title block opts out. */
[data-testid="stMarkdownContainer"]:has(> .ph) { margin-bottom: 0 !important; }
.ph { display:flex; align-items:center; gap:.7rem; flex-wrap: wrap; }
.ph-sub { color: var(--muted); font-size: .9rem; margin-top: .2rem; }
.facts { display:flex; flex-wrap:wrap; gap:.1rem 1.1rem; } .fact { white-space: nowrap; }
[class*="st-key-head_"] { flex-wrap: nowrap !important; }
[class*="st-key-head_"] > [data-testid="stElementContainer"]:has(.ph), [class*="st-key-batch_head"] > [data-testid="stElementContainer"]:has(h3) {
  flex: 1 1 auto !important; width: auto !important; min-width: 0; }
[class*="st-key-batch_head"] { flex-wrap: nowrap !important; margin-bottom: .4rem; }
[class*="st-key-batch_head"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[class*="st-key-head_action"] button { white-space: nowrap; }
[data-testid="stHeaderActionElements"] { display: none !important; }
[class*="st-key-inv_actions"] { gap: .5rem !important; flex-wrap: nowrap !important; }
[data-testid="stMarkdownContainer"]:has(> .key:last-child) { margin-bottom: 0 !important; }
[class*="st-key-inv_actions"] button { white-space: nowrap; }

/* ---------- responsive: side-by-side sections stack on a narrow window ---------- */
@media (max-width: 1240px) {
  [class*="st-key-stack_"] [data-testid="stHorizontalBlock"]:not([data-testid="stColumn"] *) { flex-wrap: wrap; }
  [class*="st-key-stack_"] [data-testid="stHorizontalBlock"]:not([data-testid="stColumn"] *) > [data-testid="stColumn"] {
    min-width: 100% !important; flex: 1 1 100% !important; }
}
/* the invoice list keeps its columns and scrolls sideways rather than wrapping every cell */
[class*="st-key-inbox_list"] { overflow-x: auto; padding-bottom: .2rem; }
[class*="st-key-inbox_list"] > * { min-width: 60rem; }
.crumb { font-size: .84rem; color: var(--muted); margin-bottom: .35rem; }
.crumb a { color: var(--muted); text-decoration: none; } .crumb a:hover { color: var(--ink); }
/* invoice page: Back button + breadcrumb on one line */
[class*="st-key-backbar"] { margin-bottom: .35rem; gap: .6rem !important; }
[class*="st-key-backbar"] .stButton button { min-height: 1.9rem; padding: .15rem .7rem .15rem .5rem; font-size: .84rem; margin-right: .3rem; }
[class*="st-key-backbar"] .crumb { margin: 0; white-space: nowrap; }
[class*="st-key-backbar"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
[class*="st-key-backbar"] [data-testid="stPageLink"] a { padding: 0 !important; min-height: 0 !important; background: transparent !important; }
[class*="st-key-backbar"] [data-testid="stPageLink"] p { font-size: .84rem; color: var(--muted) !important; }
[class*="st-key-backbar"] [data-testid="stPageLink"] a:hover p { color: var(--ink) !important; text-decoration: underline; }

/* ---------- badges, flags ---------- */
.badge { display:inline-block; padding:.12rem .52rem; border-radius:999px; font-size:.78rem; font-weight:600; white-space:nowrap; line-height:1.4; }
.b-READY { background:var(--ready-bg); color:var(--ready); } .b-NEEDS_REVIEW { background:var(--review-bg); color:var(--review); }
.b-BLOCKED { background:var(--blocked-bg); color:var(--blocked); } .b-APPROVED, .b-Active { background:var(--approved-bg); color:var(--approved); }
.b-REJECTED, .b-UNREADABLE, .b-Inactive, .b-Closed { background:var(--grey-bg); color:var(--grey); }
.b-Open { background:var(--ready-bg); color:var(--ready); } .b-Partially { background:var(--review-bg); color:var(--review); }
.b-Fully { background:var(--approved-bg); color:var(--approved); }
.flag { display:inline-block; font-size:.74rem; font-weight:600; padding:.06rem .42rem; border-radius:5px; margin:0 .25rem .2rem 0; white-space:nowrap; border:1px solid; }
.f-FAIL { color:var(--blocked); border-color:var(--a-blocked-bd); background:var(--a-blocked-bg); }
.f-WARN { color:var(--review); border-color:var(--a-review-bd); background:var(--a-review-bg); }

/* ---------- cards, KPIs ---------- */
[class*="st-key-card"] { border:1px solid var(--line) !important; border-radius:10px !important; padding:1rem 1.1rem !important; background:var(--surface); }
.kpi-wrap { container-type: inline-size; }
.kpis { display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap:.75rem; margin: .2rem 0 1.4rem; }
.kpi { border:1px solid var(--line); border-radius:10px; padding:.85rem 1rem; background:var(--surface); min-width:0; }
.kpi .l { font-size:.82rem; color:var(--muted); display:flex; align-items:center; gap:.4rem; white-space:nowrap; }
.kpi .l i { width:.5rem; height:.5rem; border-radius:50%; display:inline-block; flex:none; }
.kpi .v { font-size:1.6rem; font-weight:650; margin-top:.2rem; font-variant-numeric:tabular-nums; letter-spacing:-0.01em; color:var(--ink); }
.kpi .s { font-size:.82rem; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
/* five across when there is room; otherwise three over two, sized by the space the row really has */
@container (max-width: 900px) { .kpis { grid-template-columns: repeat(6, minmax(0,1fr)); } .kpi { grid-column: span 2; }
  .kpi:nth-child(n+4) { grid-column: span 3; } }
@container (max-width: 480px) { .kpi, .kpi:nth-child(n+4) { grid-column: span 6; } }

/* ---------- tables ---------- */
.tbl, .tbl th, .tbl td, .tbl tr { border-left:none !important; border-right:none !important; border-top:none !important; background:transparent; }
.tbl { width:100%; border-collapse:collapse; font-size:.88rem; border:none !important; color:var(--ink); }
.tbl th { text-align:left; font-weight:600; color:var(--muted); font-size:.78rem; padding:.5rem .6rem; border-bottom:1px solid var(--line) !important; white-space:nowrap; }
.tbl td { padding:.6rem .6rem; border-bottom:1px solid var(--line2) !important; vertical-align:middle; }
.tbl tr:last-child td { border-bottom:none !important; }
/* first and last cells line up with the card heading above; a table too wide for its card scrolls inside it */
.tbl th:first-child, .tbl td:first-child { padding-left:0; } .tbl th:last-child, .tbl td:last-child { padding-right:0; }
.tbl td.cell-warn:last-child, .tbl td.cell-fail:last-child { padding-right:.6rem; }
.tbl td.main { min-width: 9rem; } .tbl th .sub { font-weight:500; }
.cell-warn .sub, .cell-fail .sub { font-weight:500; }
[data-testid="stMarkdownContainer"]:has(> .tbl) { overflow-x:auto; }
.tbl .r { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.tbl .sub, .rc .sub { font-size:.78rem; color:var(--muted); }
.tbl td.nw, .nw { white-space:nowrap; }
.cell-ok { color:var(--approved); } .cell-warn { background:var(--cell-warn) !important; color:var(--review); font-weight:600; }
.cell-fail { background:var(--cell-fail) !important; color:var(--blocked); font-weight:600; }
.bar { height:6px; background:var(--line2); border-radius:3px; overflow:hidden; min-width:80px; display:flex; }
.bar span { display:block; height:100%; background:var(--bar); }
.bar span.before { background:var(--bar-before); }
.key { display:flex; gap:1.1rem; font-size:.78rem; color:var(--muted); margin-top:.5rem; }
.key i { width:.6rem; height:.6rem; border-radius:2px; display:inline-block; margin-right:.35rem; vertical-align:-1px; }
details summary { cursor:pointer; }

/* ---------- row lists ---------- */
.rh { font-size:.78rem; font-weight:600; color:var(--muted); padding-bottom:.35rem; border-bottom:1px solid var(--line); white-space:nowrap; margin-bottom:.45rem; }
.rc { font-size:.88rem; line-height:1.35; padding-top:.3rem; color:var(--ink); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.rc.wrap { white-space:normal; overflow:visible; }
.rc.r { text-align:right; font-variant-numeric:tabular-nums; }
.rr { border-bottom:1px solid var(--line2); margin:.2rem 0 .15rem; }
[class*="st-key-row_"] [data-testid="stPageLink"] a { padding:0; max-width:100%; }
[class*="st-key-row_"] [data-testid="stPageLink"], [class*="st-key-row_"] [data-testid="stPageLink"] * { min-width:0; max-width:100%; }
[class*="st-key-row_"] [data-testid="stPageLink"] p { font-weight:600; font-size:.9rem; color:var(--ink) !important;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
[class*="st-key-row_"] [data-testid="stPageLink"] a:hover p { color:var(--brand) !important; text-decoration:underline; }

/* ---------- alert banner ---------- */
.alert { border-radius:10px; padding:.85rem 1rem; border:1px solid; margin:.2rem 0 1rem; color:var(--ink); }
.alert .t { font-weight:650; font-size:.95rem; } .alert .d { font-size:.88rem; margin-top:.2rem; line-height:1.45; }
.a-BLOCKED, .a-UNREADABLE { background:var(--a-blocked-bg); border-color:var(--a-blocked-bd); } .a-BLOCKED .t, .a-UNREADABLE .t { color:var(--blocked); }
.a-NEEDS_REVIEW { background:var(--a-review-bg); border-color:var(--a-review-bd); } .a-NEEDS_REVIEW .t { color:var(--review); }
.a-READY { background:var(--a-ready-bg); border-color:var(--a-ready-bd); } .a-READY .t { color:var(--ready); }
.a-APPROVED { background:var(--a-approved-bg); border-color:var(--a-approved-bd); } .a-APPROVED .t { color:var(--approved); }
.a-REJECTED { background:var(--subtle); border-color:var(--line); } .a-REJECTED .t { color:var(--grey); }

/* ---------- document viewer ---------- */
.doc { position:relative; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:#fff; }
.doc img { width:100%; display:block; }
.hl { position:absolute; border:1.5px solid #2F9E63; background:rgba(47,158,99,.10); border-radius:3px; }
.hl.low { border-color:#D08A00; background:rgba(208,138,0,.14); } .hl.line { border-color:#3149C9; background:rgba(49,73,201,.07); }
.hl span { display:none; position:absolute; top:-1.15rem; left:-1px; font-size:.62rem; font-weight:700; color:#fff; background:#2F9E63; padding:0 .3rem; border-radius:3px 3px 0 0; white-space:nowrap; }
.hl:hover span { display:block; } .hl:hover { z-index:5; }
.hl.low span { background:#D08A00; } .hl.line span { background:#3149C9; }
.doc-empty { border:1px dashed var(--strong); border-radius:8px; padding:3rem 1.2rem; text-align:center; color:var(--muted); font-size:.9rem; background:var(--subtle); }

/* ---------- fields, checks, timeline, steps ---------- */
h3.grp { margin: 1.3rem 0 .35rem !important; } .flds > h3.grp:first-child { margin-top: .9rem !important; }
.fld { display:grid; grid-template-columns: 1.1rem 6.5rem minmax(0,1fr) auto; gap:.5rem; align-items:baseline; padding:.42rem 0; border-bottom:1px solid var(--line2); font-size:.88rem; color:var(--ink); }
.fld:last-child { border-bottom:none; }
.fld .ic { font-weight:800; font-size:.8rem; } .fld .ic.ok { color:var(--ok); } .fld .ic.low { color:var(--amber); } .fld .ic.no { color:var(--faint); }
.fld .k { color:var(--muted); } .fld .v { font-weight:500; overflow-wrap:anywhere; } .fld .c { font-size:.76rem; color:var(--faint); font-variant-numeric:tabular-nums; }
.fld .p { grid-column:3; font-size:.76rem; color:var(--faint); margin-top:-.1rem; }
.chk { display:grid; grid-template-columns: 4.2rem 1fr; gap:.7rem; padding:.55rem 0; border-bottom:1px solid var(--line2); font-size:.88rem; color:var(--ink); }
.chk:last-child { border-bottom:none; }
.chk .o { font-size:.74rem; font-weight:700; } .chk .o.PASS { color:var(--approved); } .chk .o.WARN { color:var(--review); } .chk .o.FAIL { color:var(--blocked); }
.chk .e { font-size:.8rem; color:var(--muted); margin-top:.1rem; } .chk .a { font-size:.82rem; font-weight:600; margin-top:.15rem; }
.tl { position:relative; padding-left:1.2rem; color:var(--ink); }
.tl:before { content:""; position:absolute; left:.33rem; top:.4rem; bottom:.4rem; width:1px; background:var(--line); }
.ev { position:relative; padding:.1rem 0 .9rem; font-size:.88rem; }
.ev:before { content:""; position:absolute; left:-1.05rem; top:.38rem; width:.5rem; height:.5rem; border-radius:50%; background:var(--strong); }
.ev.sys:before { background:var(--brand); } .ev.ok:before { background:var(--ok); } .ev.bad:before { background:var(--blocked); }
.ev .w { font-size:.76rem; color:var(--faint); } .ev .t { font-weight:600; } .ev .d { color:var(--muted); margin-top:.1rem; line-height:1.45; }
.ev .note { background:var(--subtle); border:1px solid var(--line); border-radius:8px; padding:.45rem .65rem; margin-top:.3rem; }
.st { display:grid; grid-template-columns: 1.4rem 1fr auto; gap:.6rem; padding:.48rem 0; border-bottom:1px solid var(--line2); align-items:start; color:var(--ink); }
.st:last-child { border-bottom:none; }
.st .i { width:1.15rem; height:1.15rem; border-radius:50%; border:1.5px solid var(--strong); display:flex; align-items:center; justify-content:center; font-size:.66rem; font-weight:800; color:#fff; margin-top:.1rem; }
.st.COMPLETED .i { background:var(--ok); border-color:var(--ok); } .st.FAILED .i { background:var(--blocked); border-color:var(--blocked); }
.st.RUNNING .i { border-color:var(--brand); border-top-color:transparent; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .st.RUNNING .i { animation:none; } }
.st .n { font-size:.88rem; font-weight:600; } .st.PENDING .n, .st.SKIPPED .n { color:var(--faint); font-weight:500; }
.st .m { font-size:.8rem; color:var(--muted); margin-top:.1rem; line-height:1.4; } .st.FAILED .m { color:var(--blocked); }
.st .ms { font-size:.76rem; color:var(--faint); font-variant-numeric:tabular-nums; }
.empty { border:1px dashed var(--strong); border-radius:10px; padding:2.2rem 1.2rem; text-align:center; color:var(--muted); font-size:.9rem; background:var(--surface); }
.empty b { display:block; color:var(--ink); font-size:.98rem; margin-bottom:.2rem; }
"""


def is_dark() -> bool:
    return bool(st.session_state.get("dark_mode", False))


def apply_theme() -> None:
    css = (DARK if is_dark() else LIGHT) + BASE
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def chart_colors() -> dict:
    return ({"font": "#A3A3AD", "grid": "#26262B"} if is_dark() else {"font": "#6B6B72", "grid": "#F1F1EF"})

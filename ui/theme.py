"""Single white theme applied via CSS.

No JavaScript, no new dependencies, no restart: the app injects css_for()
once per rerun. One permanent palette: pure white surfaces, near-black
text, neutral grey borders, one restrained green accent.

Two facts drive the design. First, buttons and controls render through
wrapper layers, so every control selector below uses descendant
combinators. Direct-child selectors miss the real controls and leave
default surfaces behind while global text rules paint labels
unreadable: the white-on-white defect. kind="primary" and
kind="tertiary" follow Streamlit's own DOM convention for typed
buttons. Second, menu/dropdown popovers portal outside the app
container, so popover rules use global testid selectors and restyle
items and their hover/focus/disabled states, not just the popover
frame.

Status is never carried by colour alone. Every verdict keeps its text label.
All interactive pairs below target WCAG AA (4.5:1 text, 3:1 indicators).
"""
from __future__ import annotations

THEME = {
    "bg": "#FFFFFF", "bg2": "#F5F5F5", "cards": "#FFFFFF",
    "text": "#171717", "muted": "#374151", "helper": "#4B5563",
    "accent": "#315C42",
    "btn_pri": "#315C42", "on_btn_pri": "#FFFFFF",
    "pri_hover": "#264A36", "on_pri_hover": "#FFFFFF",
    "btn_sec": "#FFFFFF", "on_btn_sec": "#171717",
    "hover": "#E8E8E8", "on_hover": "#171717", "focus": "#2F5D8A", "print_ink": "#1A1A1A",
    "success": "#315C42", "info": "#2F5D8A", "warning": "#8C6D2F", "danger": "#B3261E",
    "border": "#E5E7EB", "input_bg": "#FFFFFF",
}


def css_for() -> str:
    """Full <style> block for the single white theme. Pure function."""
    pal = THEME
    return f"""<style>
/* pruvchat-theme:white */
:root {{
  --pruv-bg: {pal["bg"]}; --pruv-bg2: {pal["bg2"]}; --pruv-cards: {pal["cards"]};
  --pruv-text: {pal["text"]}; --pruv-muted: {pal["muted"]};
  --pruv-helper: {pal["helper"]};
  --pruv-accent: {pal["accent"]};
  --pruv-btn-pri: {pal["btn_pri"]}; --pruv-on-btn-pri: {pal["on_btn_pri"]};
  --pruv-pri-hover: {pal["pri_hover"]}; --pruv-on-pri-hover: {pal["on_pri_hover"]};
  --pruv-btn-sec: {pal["btn_sec"]}; --pruv-on-btn-sec: {pal["on_btn_sec"]};
  --pruv-hover: {pal["hover"]}; --pruv-on-hover: {pal["on_hover"]};
  --pruv-focus: {pal["focus"]};
  --pruv-success: {pal["success"]}; --pruv-info: {pal["info"]};
  --pruv-warning: {pal["warning"]}; --pruv-danger: {pal["danger"]};
  --pruv-border: {pal["border"]}; --pruv-input: {pal["input_bg"]};
  --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px;
  --sp-5: 24px; --sp-6: 32px; --sp-7: 48px;
  --r-sm: 8px; --r-md: 10px; --r-lg: 12px;
}}
.stApp {{ background-color: var(--pruv-bg); }}
.stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li,
.stApp span, .stApp label, .stApp div {{
  color: var(--pruv-text);
}}
.stApp h1, .stApp h2, .stApp h3, [data-testid="stSubheader"] {{
  word-break: normal; overflow-wrap: break-word; text-wrap: balance;
}}
.stApp h1 {{ font-size: 1.75rem; line-height: 1.3; }}
.stApp h2 {{ font-size: 1.375rem; line-height: 1.35; }}
.stApp h3, [data-testid="stSubheader"] {{ font-size: 1.125rem; line-height: 1.4; }}
.stApp p, .stApp li {{ line-height: 1.55; }}
.block-container {{
  max-width: 72rem; padding-left: var(--sp-6); padding-right: var(--sp-6);
}}
[data-testid="stSidebar"] {{ background-color: var(--pruv-bg2); }}
.stApp a {{ color: var(--pruv-accent); text-decoration: underline; }}
.stApp a:hover {{ color: var(--pruv-accent); text-decoration: underline; }}
.stApp a:visited {{ color: var(--pruv-muted); }}
.stApp a[target="_blank"]::after {{
  content: " ↗"; font-size: 0.85em;
}}
.stApp hr {{ border-color: var(--pruv-border); }}
.stCaption, [data-testid="stCaption"], [data-testid="stMetricLabel"] {{
  color: var(--pruv-helper);
}}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span,
[data-testid="stWidgetLabel"] label {{
  color: var(--pruv-text);
}}
/* Buttons render through wrapper layers (proven from the 1.66.1 Button,
   DownloadButton, LinkButton, and Popover chunks: testid div > widget
   wrapper > button/anchor), so every control selector below uses descendant
   combinators. Direct-child selectors miss the real controls and leave
   light emotion surfaces behind while global text rules paint labels
   light: the white-on-white defect. kind="primary" follows Streamlit's
   own DOM convention for typed buttons. */
div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button,
div[data-testid="stLinkButton"] a {{
  background: var(--pruv-btn-sec); color: var(--pruv-on-btn-sec);
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
  min-height: 2.75rem; text-decoration: none;
}}
div[data-testid="stButton"] button span,
div[data-testid="stButton"] button p,
div[data-testid="stButton"] button div,
div[data-testid="stDownloadButton"] button span,
div[data-testid="stDownloadButton"] button p,
div[data-testid="stDownloadButton"] button div,
div[data-testid="stLinkButton"] a span,
div[data-testid="stLinkButton"] a p,
div[data-testid="stLinkButton"] a div {{
  color: inherit;
}}
div[data-testid="stButton"] button[kind="primary"],
div[data-testid="stDownloadButton"] button[kind="primary"] {{
  background: var(--pruv-btn-pri); border-color: var(--pruv-btn-pri);
  color: var(--pruv-on-btn-pri);
}}
div[data-testid="stButton"] button:hover,
div[data-testid="stDownloadButton"] button:hover,
div[data-testid="stLinkButton"] a:hover {{
  background: var(--pruv-hover); border-color: var(--pruv-hover);
  color: var(--pruv-on-hover); text-decoration: none;
}}
div[data-testid="stButton"] button[kind="primary"]:hover,
div[data-testid="stDownloadButton"] button[kind="primary"]:hover {{
  background: var(--pruv-pri-hover); border-color: var(--pruv-pri-hover);
  color: var(--pruv-on-pri-hover);
}}
div[data-testid="stButton"] button[kind="primary"]:active,
div[data-testid="stDownloadButton"] button[kind="primary"]:active {{
  background: var(--pruv-pri-hover); border-color: var(--pruv-pri-hover);
  color: var(--pruv-on-pri-hover);
}}
div[data-testid="stButton"] button:focus-visible,
div[data-testid="stDownloadButton"] button:focus-visible,
div[data-testid="stLinkButton"] a:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: 2px;
}}
div[data-testid="stButton"] button:active,
div[data-testid="stDownloadButton"] button:active,
div[data-testid="stLinkButton"] a:active {{
  background: var(--pruv-bg2); color: var(--pruv-text);
}}
div[data-testid="stButton"] button:hover span,
div[data-testid="stDownloadButton"] button:hover span,
div[data-testid="stButton"] button:hover p,
div[data-testid="stDownloadButton"] button:hover p,
div[data-testid="stButton"] button:hover div,
div[data-testid="stDownloadButton"] button:hover div,
div[data-testid="stButton"] button:hover svg,
div[data-testid="stDownloadButton"] button:hover svg,
div[data-testid="stButton"] button:focus-visible span,
div[data-testid="stDownloadButton"] button:focus-visible span,
div[data-testid="stButton"] button:focus-visible p,
div[data-testid="stDownloadButton"] button:focus-visible p,
div[data-testid="stButton"] button:active span,
div[data-testid="stDownloadButton"] button:active span,
div[data-testid="stButton"] button:active p,
div[data-testid="stDownloadButton"] button:active p,
div[data-testid="stLinkButton"] a:hover span,
div[data-testid="stLinkButton"] a:hover p,
div[data-testid="stLinkButton"] a:hover div,
div[data-testid="stLinkButton"] a:focus-visible span,
div[data-testid="stLinkButton"] a:focus-visible p,
div[data-testid="stLinkButton"] a:active span,
div[data-testid="stLinkButton"] a:active p {{
  color: inherit;
}}
div[data-testid="stButton"] button:disabled,
div[data-testid="stDownloadButton"] button:disabled {{
  background: var(--pruv-bg2); color: var(--pruv-muted);
  border-color: var(--pruv-border); cursor: not-allowed;
}}
div[data-testid="stButton"] button:disabled span,
div[data-testid="stDownloadButton"] button:disabled span,
div[data-testid="stButton"] button:disabled p,
div[data-testid="stDownloadButton"] button:disabled p {{
  color: inherit;
}}
div[data-testid="stLinkButton"] a[aria-disabled="true"] {{
  background: var(--pruv-bg2); color: var(--pruv-muted);
  border-color: var(--pruv-border); cursor: not-allowed; text-decoration: none;
}}
div[data-testid="stLinkButton"] a[aria-disabled="true"] span,
div[data-testid="stLinkButton"] a[aria-disabled="true"] p {{
  color: inherit;
}}
/* Tertiary text buttons (Overview Explore links): transparent surface with
   accent text. kind="tertiary" when Streamlit forwards it; st-key anchors
   cover the card buttons regardless. Nested labels inherit the accent from
   the shared rule above. Underline on hover keeps the surface calm. */
div[data-testid="stButton"] button[kind="tertiary"],
.st-key-go_req div[data-testid="stButton"] button,
.st-key-go_dis div[data-testid="stButton"] button,
.st-key-go_cus div[data-testid="stButton"] button,
.st-key-go_visa div[data-testid="stButton"] button,
.st-key-nav_0 div[data-testid="stButton"] button,
.st-key-nav_1 div[data-testid="stButton"] button,
.st-key-nav_2 div[data-testid="stButton"] button,
.st-key-nav_3 div[data-testid="stButton"] button,
.st-key-nav_4 div[data-testid="stButton"] button,
.st-key-guide_skip div[data-testid="stButton"] button,
.st-key-guide_close div[data-testid="stButton"] button,
.st-key-guide_show div[data-testid="stButton"] button {{
  background: transparent; border-color: transparent; color: var(--pruv-accent);
  min-height: 2.75rem; text-decoration: none;
}}
div[data-testid="stButton"] button[kind="tertiary"]:hover,
.st-key-go_req div[data-testid="stButton"] button:hover,
.st-key-go_dis div[data-testid="stButton"] button:hover,
.st-key-go_cus div[data-testid="stButton"] button:hover,
.st-key-go_visa div[data-testid="stButton"] button:hover,
.st-key-nav_0 div[data-testid="stButton"] button:hover,
.st-key-nav_1 div[data-testid="stButton"] button:hover,
.st-key-nav_2 div[data-testid="stButton"] button:hover,
.st-key-nav_3 div[data-testid="stButton"] button:hover,
.st-key-nav_4 div[data-testid="stButton"] button:hover,
.st-key-guide_skip div[data-testid="stButton"] button:hover,
.st-key-guide_close div[data-testid="stButton"] button:hover,
.st-key-guide_show div[data-testid="stButton"] button:hover {{
  background: transparent; border-color: transparent; color: var(--pruv-accent);
  text-decoration: underline;
}}
div[data-testid="stButton"] button[kind="tertiary"]:active,
.st-key-go_req div[data-testid="stButton"] button:active,
.st-key-go_dis div[data-testid="stButton"] button:active,
.st-key-go_cus div[data-testid="stButton"] button:active,
.st-key-go_visa div[data-testid="stButton"] button:active,
.st-key-nav_0 div[data-testid="stButton"] button:active,
.st-key-nav_1 div[data-testid="stButton"] button:active,
.st-key-nav_2 div[data-testid="stButton"] button:active,
.st-key-nav_3 div[data-testid="stButton"] button:active,
.st-key-nav_4 div[data-testid="stButton"] button:active,
.st-key-guide_skip div[data-testid="stButton"] button:active,
.st-key-guide_close div[data-testid="stButton"] button:active,
.st-key-guide_show div[data-testid="stButton"] button:active {{
  background: var(--pruv-hover); border-color: var(--pruv-hover);
  color: var(--pruv-on-hover);
}}
div[data-testid="stButton"] button[kind="tertiary"]:disabled,
.st-key-go_req div[data-testid="stButton"] button:disabled,
.st-key-go_dis div[data-testid="stButton"] button:disabled,
.st-key-go_cus div[data-testid="stButton"] button:disabled,
.st-key-go_visa div[data-testid="stButton"] button:disabled,
.st-key-nav_0 div[data-testid="stButton"] button:disabled,
.st-key-nav_1 div[data-testid="stButton"] button:disabled,
.st-key-nav_2 div[data-testid="stButton"] button:disabled,
.st-key-nav_3 div[data-testid="stButton"] button:disabled,
.st-key-nav_4 div[data-testid="stButton"] button:disabled,
.st-key-guide_skip div[data-testid="stButton"] button:disabled,
.st-key-guide_close div[data-testid="stButton"] button:disabled,
.st-key-guide_show div[data-testid="stButton"] button:disabled {{
  background: transparent; border-color: transparent; color: var(--pruv-muted);
  cursor: not-allowed; text-decoration: none;
}}
/* Header Search/Help/Settings popover triggers: same tertiary treatment so
   the header stays calm. Transparent surface, accent text and icons. */
div[data-testid="stPopoverButton"] button {{
  background: transparent; border-color: transparent; color: var(--pruv-accent);
  min-height: 2.75rem;
}}
div[data-testid="stPopoverButton"] button span,
div[data-testid="stPopoverButton"] button p,
div[data-testid="stPopoverButton"] button div,
div[data-testid="stPopoverButton"] button svg {{
  color: inherit;
}}
div[data-testid="stPopoverButton"] button:hover {{
  background: transparent; border-color: transparent; color: var(--pruv-accent);
  text-decoration: underline;
}}
div[data-testid="stPopoverButton"] button:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: 2px;
}}
div[data-testid="stPopoverButton"] button:active {{
  background: var(--pruv-hover); color: var(--pruv-on-hover);
}}
div[data-testid="stPopoverButton"] button:disabled {{
  background: transparent; border-color: transparent; color: var(--pruv-muted);
  cursor: not-allowed;
}}
div[data-testid="stPopoverButton"] button:disabled span,
div[data-testid="stPopoverButton"] button:disabled p {{
  color: inherit;
}}
[data-testid="stHeader"], [data-testid="stToolbar"] {{
  background-color: var(--pruv-bg);
}}
[data-testid="stToolbar"] button {{
  background: var(--pruv-btn-sec); color: var(--pruv-on-btn-sec);
  border: 1px solid var(--pruv-border); border-radius: var(--r-sm);
}}
[data-testid="stToolbar"] button span, [data-testid="stToolbar"] button p,
[data-testid="stToolbar"] button div {{
  color: inherit;
}}
[data-testid="stToolbar"] svg, [data-testid="stToolbar"] [aria-hidden="true"] {{
  color: var(--pruv-text) !important;
}}
[data-testid="stAppDeployButton"] button {{
  background: var(--pruv-btn-sec); color: var(--pruv-on-btn-sec);
  border: 1px solid var(--pruv-border); border-radius: var(--r-sm);
}}
[data-testid="stToolbar"] button:hover {{
  background: var(--pruv-hover); border-color: var(--pruv-hover);
  color: var(--pruv-on-hover);
}}
[data-testid="stToolbar"] button:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: 2px;
}}
[data-testid="stToolbar"] button:active {{
  background: var(--pruv-bg2); color: var(--pruv-text);
}}
[data-testid="stToolbar"] button:hover span,
[data-testid="stToolbar"] button:hover p,
[data-testid="stToolbar"] button:hover svg,
[data-testid="stToolbar"] button:focus-visible span,
[data-testid="stToolbar"] button:focus-visible p,
[data-testid="stToolbar"] button:active span,
[data-testid="stToolbar"] button:active p {{
  color: inherit;
}}
[data-testid="stToolbar"] button:disabled {{
  background: var(--pruv-bg2); color: var(--pruv-muted);
  border-color: var(--pruv-border); cursor: not-allowed;
}}
[data-testid="stMainMenuPopover"] {{
  background: var(--pruv-cards); color: var(--pruv-text);
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
}}
[data-testid^="stMainMenuItem"] {{
  background: transparent; color: var(--pruv-text); border-radius: var(--r-sm);
}}
[data-testid^="stMainMenuItem"]:hover {{
  background: var(--pruv-hover); color: var(--pruv-on-hover);
}}
[data-testid^="stMainMenuItem"]:hover span,
[data-testid^="stMainMenuItem"]:hover p {{
  color: var(--pruv-on-hover);
}}
[data-testid^="stMainMenuItem"]:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: -2px;
}}
[data-testid^="stMainMenuItem"][aria-disabled="true"] {{
  color: var(--pruv-muted);
}}
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea {{
  background: var(--pruv-input); color: var(--pruv-text);
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
}}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder {{
  color: var(--pruv-helper);
}}
[data-testid="stTextInput"] input:focus-visible,
[data-testid="stTextArea"] textarea:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: 1px;
  border-color: var(--pruv-focus);
}}
/* 1.66.1 DOM: no baseweb anywhere in the installed bundle. The trigger
   is a combobox input plus a toggle button inside the testid container;
   the popup portals out, so role selectors stay global and tag-agnostic.
   The trigger keeps one stable surface; open/focus feedback is a chevron
   colour change only, never a background wash. */
[data-testid="stSelectbox"] > div,
[data-testid="stSelectbox"] > div:hover,
[data-testid="stSelectbox"] > div:focus-within {{
  background: var(--pruv-input); border-radius: var(--r-md);
}}
[data-testid="stSelectbox"] input[role="combobox"] {{
  color: var(--pruv-text); background: transparent;
}}
[data-testid="stSelectbox"] input[role="combobox"]::placeholder {{
  color: var(--pruv-helper);
}}
[data-testid="stSelectbox"] button svg {{ color: var(--pruv-muted); }}
[data-testid="stSelectbox"]:focus-within button svg {{
  color: var(--pruv-focus);
}}
/* The trigger control is NOT always the direct child: the ComboBox subtree
   wraps it (proven from the Selectbox chunk: a trigger div holding the value
   input plus toggle buttons). The unstyled control keeps the light emotion
   background while global text rules paint the value light, which reads as
   white on white. Target the trigger structurally: the div holding the input.
   Testid-scoped; nothing outside selectboxes is touched. */
[data-testid="stSelectbox"] div:has(> input) {{
  background: var(--pruv-input); color: var(--pruv-text);
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
}}
[data-testid="stSelectbox"] div:has(> input):hover,
[data-testid="stSelectbox"] div:has(> input):focus-within {{
  background: var(--pruv-input); border-color: var(--pruv-focus);
}}
[data-testid="stSelectbox"] div:has(> input) > input {{
  background: transparent; color: var(--pruv-text);
}}
[data-testid="stSelectbox"] div:has(> input) input::placeholder {{
  color: var(--pruv-helper);
}}
[data-testid="stSelectbox"] div:has(> input) span {{
  color: inherit;
}}
[data-testid="stSelectbox"] div:has(> input) button svg {{
  color: var(--pruv-muted);
}}
[data-testid="stSelectbox"]:focus-within div:has(> input) button svg {{
  color: var(--pruv-focus);
}}
[role="listbox"] {{
  background: var(--pruv-cards); color: var(--pruv-text);
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
}}
[role="option"] {{
  background: transparent; color: var(--pruv-text);
}}
[role="option"]:hover, [role="option"][aria-selected="true"] {{
  background: var(--pruv-hover); color: var(--pruv-on-hover);
}}
[role="option"]:hover span, [role="option"]:hover p,
[role="option"][aria-selected="true"] span,
[role="option"][aria-selected="true"] p {{
  color: var(--pruv-on-hover);
}}
[role="option"] svg {{
  color: inherit;
}}
[data-testid="stRadio"] svg, [data-testid="stCheckbox"] svg {{
  color: var(--pruv-accent);
}}
[data-testid="stRadioOption"]:hover {{
  background: var(--pruv-hover); border-radius: var(--r-sm);
}}
[data-testid="stRadioOption"]:hover span,
[data-testid="stRadioOption"]:hover p {{
  color: var(--pruv-on-hover);
}}
[data-testid="stRadioOption"]:focus-within {{
  outline: 2px solid var(--pruv-focus); outline-offset: -2px;
}}
[data-testid="stCheckbox"]:hover {{
  background: var(--pruv-hover); border-radius: var(--r-sm);
}}
[data-testid="stCheckbox"]:hover span,
[data-testid="stCheckbox"]:hover p {{
  color: var(--pruv-on-hover);
}}
[data-testid="stCheckbox"]:focus-within {{
  outline: 2px solid var(--pruv-focus); outline-offset: -2px;
}}
[data-testid="stFileUploader"] section {{
  background: var(--pruv-input); border-radius: var(--r-md);
  border-color: var(--pruv-border);
}}
[data-testid="stFileUploader"] section:hover {{
  border-color: var(--pruv-focus);
}}
[data-testid="stFileUploader"] button {{
  background: var(--pruv-btn-sec); color: var(--pruv-on-btn-sec);
  border: 1px solid var(--pruv-border); border-radius: var(--r-sm);
}}
[data-testid="stFileUploader"] button:hover {{
  background: var(--pruv-hover); color: var(--pruv-on-hover);
}}
[data-testid="stFileUploader"] button:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: 2px;
}}
[data-testid="stFileUploader"] button:active {{
  background: var(--pruv-bg2); color: var(--pruv-text);
}}
[data-testid="stFileUploader"] button span,
[data-testid="stFileUploader"] button p,
[data-testid="stFileUploader"] button div {{
  color: inherit;
}}
[data-testid="stFileUploader"] button:hover span,
[data-testid="stFileUploader"] button:hover p,
[data-testid="stFileUploader"] button:focus-visible span,
[data-testid="stFileUploader"] button:focus-visible p,
[data-testid="stFileUploader"] button:active span,
[data-testid="stFileUploader"] button:active p {{
  color: inherit;
}}
[data-testid="stFileUploader"] button:disabled {{
  background: var(--pruv-bg2); color: var(--pruv-muted);
  border-color: var(--pruv-border); cursor: not-allowed;
}}
.stAlert {{
  background: var(--pruv-cards); border: 1px solid var(--pruv-border);
  border-radius: var(--r-md); padding: 20px 24px;
}}
[data-testid="stExpander"] {{
  border: 1px solid var(--pruv-border); border-radius: var(--r-md);
}}
/* 1.66.1 DOM: testid > details > summary (proven from the installed
   bundle via detailsRef/summaryRef; the old div-based header selector
   never matched). One stable header surface in default, hover, focus,
   active, open, and closed states. Feedback is a chevron colour change
   plus a focus ring, never a background wash. */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary:hover,
[data-testid="stExpander"] summary:focus-visible,
[data-testid="stExpander"] summary:active,
[data-testid="stExpander"] details[open] > summary {{
  background: var(--pruv-cards); color: var(--pruv-text);
  border-radius: var(--r-sm);
}}
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary div,
[data-testid="stExpander"] summary svg,
[data-testid="stExpander"] summary:hover span,
[data-testid="stExpander"] summary:hover p,
[data-testid="stExpander"] summary:hover div,
[data-testid="stExpander"] summary:focus-visible span,
[data-testid="stExpander"] summary:focus-visible p,
[data-testid="stExpander"] summary:active span,
[data-testid="stExpander"] summary:active p {{
  color: inherit; background: transparent;
}}
[data-testid="stExpander"] summary:focus-visible {{
  outline: 2px solid var(--pruv-focus); outline-offset: -2px;
}}
[data-testid="stExpander"] summary:hover svg,
[data-testid="stExpander"] details[open] > summary svg {{
  color: var(--pruv-accent); background: transparent;
}}
[data-testid="stExpanderDetails"] {{
  color: var(--pruv-text);
}}
[data-testid="stDialog"], [role="dialog"] {{
  background: var(--pruv-cards); color: var(--pruv-text);
  border: 1px solid var(--pruv-border); border-radius: var(--r-lg);
}}
[data-testid="stProgressBarTrack"] {{
  background: var(--pruv-bg2); border: 1px solid var(--pruv-border);
}}
[data-testid="stProgressBarTrack"] > div {{
  background: var(--pruv-accent);
}}
/* Restrained feedback motion on interactive elements; the reduced-motion
   block below switches it off, including inside the portaled menu. */
div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button,
div[data-testid="stLinkButton"] a, div[data-testid="stPopoverButton"] button,
.stApp a,
[data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) [data-testid="stVerticalBlockBorderWrapper"],
[role="option"], [data-testid="stRadioOption"], [data-testid="stCheckbox"] {{
  transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease;
}}
@media (prefers-reduced-motion: reduce) {{
  .stApp *, .stApp *::before, .stApp *::after {{
    animation-duration: 0.01ms !important; transition-duration: 0.01ms !important;
  }}
  [role="listbox"] *, [role="option"] {{
    animation-duration: 0.01ms !important; transition-duration: 0.01ms !important;
  }}
}}
[data-testid="stMetric"] {{
  background: var(--pruv-bg2); border: 1px solid var(--pruv-border);
  border-radius: var(--r-md); padding: var(--sp-2) var(--sp-3);
}}
[data-testid="stMetricValue"] {{ color: var(--pruv-text); }}
[data-testid="stVerticalBlockBorderWrapper"] {{
  border-color: var(--pruv-border); border-radius: var(--r-md);
}}
/* Overview card rows: the app renders two rows of two cards at desktop
   widths, one column below 700px. Rows are scoped by the card button keys
   they contain, so form and navigation rows never match. */
@media (max-width: 700px) {{
  [data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) {{
    flex-wrap: wrap;
  }}
  [data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) > [data-testid="column"] {{
    flex: 1 1 100%;
  }}
}}
/* Overview cards: equal heights with bottom-anchored Explore links. Columns
   stretch equally by default; the bordered wrapper fills its column and
   stacks content so the action sits at the foot. No fixed heights anywhere,
   so nothing can clip. */
[data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) > [data-testid="column"] > [data-testid="stVerticalBlockBorderWrapper"] {{
  flex: 1 1 auto; display: flex; flex-direction: column;
}}
[data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) [data-testid="stVerticalBlock"] {{
  flex: 1 1 auto; display: flex; flex-direction: column;
}}
[data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) [data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stButton"] {{
  margin-top: auto; padding-top: var(--sp-3);
}}
[data-testid="stHorizontalBlock"]:has(.st-key-go_req, .st-key-go_cus) [data-testid="stVerticalBlockBorderWrapper"]:hover {{
  border-color: var(--pruv-accent);
}}
@media (max-width: 640px) {{
  .block-container {{ padding-left: var(--sp-4); padding-right: var(--sp-4); }}
  [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
  [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
    flex: 1 1 16rem; min-width: min(100%, 16rem);
  }}
}}
@media print {{
  [data-testid="stSidebar"], [data-testid="stHeader"], [data-testid="stToolbar"],
  [data-testid="stMainMenuPopover"], [data-testid="stAppDeployButton"],
  div[data-testid="stButton"], div[data-testid="stDownloadButton"],
  div[data-testid="stLinkButton"], div[data-testid="stPopoverButton"],
  [data-testid="stFileUploader"],
  [data-testid="stRadio"], [data-testid="stCheckbox"], [data-testid="stSelectbox"],
  [data-testid="stTextInput"], [data-testid="stTextArea"],
  [data-testid="stProgressBar"], [data-testid="stStatusWidget"],
  button, input, textarea, select {{
    display: none !important;
  }}
  .stApp, .stApp * {{
    background: #FFFFFF !important; color: #1A1A1A !important;
    border-color: var(--pruv-border) !important; box-shadow: none !important;
    text-shadow: none !important;
  }}
  .block-container {{ max-width: 100%; }}
  details > summary {{ display: none !important; }}
  details > :not(summary) {{ display: block !important; }}
  [data-testid="stVerticalBlockBorderWrapper"], [data-testid="stMetric"],
  h1, h2, h3 {{
    break-inside: avoid;
  }}
}}
</style>"""

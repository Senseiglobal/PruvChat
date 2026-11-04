"""Single white theme: palette CSS, no-JS guarantee. Pure offline."""
import re

import ui
import ui.theme as _theme_mod
from ui.theme import THEME, css_for


def test_single_white_theme_exposed():
    css = css_for()
    assert "pruvchat-theme:white" in css
    assert ui.__all__ == ["css_for"]
    for retired in ("THEMES", "LIGHT", "DARK", "resolve_theme"):
        assert not hasattr(_theme_mod, retired), retired


def test_no_dark_references_remain():
    assert "dark" not in css_for().lower()


def test_css_covers_key_components():
    css = css_for()
    for var in ("--pruv-bg", "--pruv-text", "--pruv-accent", "--pruv-border",
                "--pruv-helper"):
        assert var in css
    for sel in (".stApp", "stSidebar", "stButton", "stAlert", "stExpander",
                "stTextInput", "stTextArea", "stMetric", "stDownloadButton"):
        assert sel in css, sel
    assert THEME["bg"] in css and THEME["text"] in css


def test_css_has_no_javascript():
    lowered = css_for().lower()
    assert "<script" not in lowered and "javascript:" not in lowered


def test_white_palette_is_pure_white_and_neutral_grey():
    assert {k: THEME[k] for k in ("bg", "bg2", "cards", "text", "muted", "border",
                                 "accent", "btn_pri", "on_btn_pri", "btn_sec",
                                 "on_btn_sec", "hover", "on_hover", "focus",
                                 "input_bg")} == {
        "bg": "#FFFFFF", "bg2": "#F5F5F5", "cards": "#FFFFFF",
        "text": "#171717", "muted": "#374151", "border": "#E5E7EB",
        "accent": "#315C42",
        "btn_pri": "#315C42", "on_btn_pri": "#FFFFFF",
        "btn_sec": "#FFFFFF", "on_btn_sec": "#171717",
        "hover": "#E8E8E8", "on_hover": "#171717", "focus": "#2F5D8A",
        "input_bg": "#FFFFFF"}
    for key in ("bg", "bg2", "cards", "input_bg", "btn_sec", "hover"):
        r, g, b = (int(THEME[key][i:i + 2], 16) for i in (1, 3, 5))
        assert g - max(r, b) == 0, f"{key} must be a pure neutral grey"
    r, g, b = (int(THEME["border"][i:i + 2], 16) for i in (1, 3, 5))
    assert max(r, g, b) - min(r, g, b) <= 6, "border must be near-neutral grey"
    css = css_for()
    for retired in ("#FAF7F2", "#F1ECE2", "#E7E2D4", "#DCD4C2",  # warm whites
                    "#121416", "#1C1F23", "#262A2F", "#3A3F45",  # charcoal surfaces
                    "#8DA9C4", "#B9BEC5",  # dark accents/text
                    "#4A6741", "#3B5233", "#23282B", "#5C6560",
                    "#D8D8D8", "#52525B"):  # previous green-grey scheme
        assert retired not in css, retired
    assert THEME["helper"] == "#4B5563"


def test_type_scale_sets_hierarchy_and_line_spacing():
    css = css_for()
    assert ".stApp h1 { font-size: 1.75rem; line-height: 1.3; }" in css
    assert ".stApp h2 { font-size: 1.375rem; line-height: 1.35; }" in css
    assert (".stApp h3, [data-testid=\"stSubheader\"] "
            "{ font-size: 1.125rem; line-height: 1.4; }") in css
    assert ".stApp p, .stApp li { line-height: 1.55; }" in css


def _luminance(hexstr):
    rgb = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_contrast_meets_aa():
    pal = THEME
    assert _ratio(pal["text"], pal["bg"]) >= 4.5
    assert _ratio(pal["muted"], pal["bg"]) >= 4.5
    assert _ratio(pal["text"], pal["cards"]) >= 4.5
    assert _ratio(pal["text"], pal["bg2"]) >= 4.5
    assert _ratio(pal["muted"], pal["cards"]) >= 4.5
    # Buttons across default, hover, pressed, and disabled-adjacent states.
    assert _ratio(pal["on_btn_pri"], pal["btn_pri"]) >= 4.5
    assert _ratio(pal["on_btn_sec"], pal["btn_sec"]) >= 4.5
    assert _ratio(pal["on_hover"], pal["hover"]) >= 4.5
    assert _ratio(pal["on_pri_hover"], pal["pri_hover"]) >= 4.5
    assert _ratio(pal["muted"], pal["bg2"]) >= 4.5  # disabled treatment
    # Tertiary text buttons: accent on card white, muted when disabled.
    assert _ratio(pal["accent"], pal["cards"]) >= 4.5
    # Helper text (captions, placeholders) on white surfaces.
    assert _ratio(pal["helper"], pal["bg"]) >= 4.5
    assert _ratio(pal["helper"], pal["cards"]) >= 4.5
    assert _ratio(pal["helper"], pal["input_bg"]) >= 4.5
    # Dropdown trigger and expander header pairs (stable surfaces).
    assert _ratio(pal["text"], pal["input_bg"]) >= 4.5
    assert _ratio(pal["muted"], pal["input_bg"]) >= 3.0  # placeholder/chevron
    assert _ratio(pal["accent"], pal["cards"]) >= 3.0  # expander chevron
    assert _ratio(pal["focus"], pal["input_bg"]) >= 3.0  # dropdown focus
    # Non-text indicators: focus ring and status borders (3:1 floor).
    assert _ratio(pal["focus"], pal["bg"]) >= 3.0
    assert _ratio(pal["warning"], pal["bg"]) >= 3.0
    assert _ratio(pal["accent"], pal["bg"]) >= 4.5  # links carry meaning
    assert _ratio(pal["accent"], pal["bg2"]) >= 3.0  # progress bar on track
    for pal_key in ("text", "muted", "accent"):  # popup options on cards
        assert _ratio(THEME[pal_key], THEME["cards"]) >= 4.5


def test_toolbar_deploy_and_menu_selectors_present():
    css = css_for()
    for sel in ('[data-testid="stHeader"]', '[data-testid="stToolbar"]',
                '[data-testid="stAppDeployButton"] button',
                '[data-testid="stMainMenuPopover"]',
                '[data-testid^="stMainMenuItem"]',
                '[data-testid^="stMainMenuItem"]:hover',
                '[data-testid^="stMainMenuItem"]:focus-visible'):
        assert sel in css, sel


def test_button_interaction_states_keep_palette_contrast():
    css = css_for()
    for sel in ('button:hover', 'button:focus-visible', 'button:active'):
        assert f'stButton"] {sel}' in css, sel
        assert f'stToolbar"] button:{sel.split(":")[1]}' in css, sel
    assert 'stToolbar"] button:disabled' in css
    # States must reuse tested palette pairs — no one-off hex colours.
    assert set(re.findall(r"#[0-9A-Fa-f]{6}", css)) <= set(THEME.values())


def test_button_scheme_green_primary_white_secondary():
    assert {k: THEME[k] for k in ("btn_pri", "on_btn_pri", "pri_hover", "on_pri_hover",
                                 "btn_sec", "on_btn_sec")} == {
        "btn_pri": "#315C42", "on_btn_pri": "#FFFFFF",
        "pri_hover": "#264A36", "on_pri_hover": "#FFFFFF",
        "btn_sec": "#FFFFFF", "on_btn_sec": "#171717"}


def test_tertiary_buttons_are_transparent_with_accent_text():
    css = css_for()
    assert 'button[kind="tertiary"]' in css
    for key in ("go_req", "go_dis", "go_cus", "go_visa",
                "nav_0", "nav_1", "nav_2", "nav_3", "nav_4",
                "guide_skip", "guide_close", "guide_show"):
        assert f".st-key-{key}" in css, key
    for sel in ('button[kind="tertiary"]:hover',
                'button[kind="tertiary"]:active',
                'button[kind="tertiary"]:disabled',
                'stPopoverButton"] button {',
                'stPopoverButton"] button:hover',
                'stPopoverButton"] button:disabled'):
        assert sel in css, sel
    plain = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    tert = re.findall(r"([^{}]*button\[kind=\"tertiary\"\][^{}]*)\{([^{}]*)}", plain)
    base = [body for sel, body in tert if ":" not in sel]
    assert len(base) == 1, "tertiary base rule missing"
    assert "background: transparent" in base[0]
    assert "color: var(--pruv-accent)" in base[0]
    blocks = re.findall(r"([^{}]*stPopoverButton[^{}]*button[^{}]*)\{([^{}]*)}", css)
    base = [body for sel, body in blocks if sel.strip().endswith("button")]
    assert base, "popover trigger base rule missing"
    for body in base:
        assert "background: transparent" in body
        assert "color: var(--pruv-accent)" in body


def test_button_state_rules_keep_text_with_surface():
    css = css_for()
    for sel in ('button[kind="primary"]:hover',
                'button[kind="primary"]:active',
                'button:hover span',
                'button:hover p',
                'button:hover div',
                'button:hover svg',
                'button:focus-visible span',
                'button:focus-visible p',
                'button:active span',
                'button:active p',
                'button:disabled span',
                'button:disabled p',
                'cursor: not-allowed'):
        assert sel in css, sel


def test_toolbar_and_deploy_are_styled_not_hidden():
    screen = css_for().split("@media print")[0]  # print hiding is separate
    compact = screen.replace(" ", "").lower()
    assert "display:none" not in compact
    assert "visibility:hidden" not in compact
    assert "stAppDeployButton" in css_for()


def test_css_covers_sidebar_widgets_alerts_and_inputs():
    css = css_for()
    for sel in ("stSidebar", "stWidgetLabel", "stRadio", "stCheckbox", "stSelectbox",
                "listbox", "stButton", "stDownloadButton", "stAlert",
                "stTextInput", "stTextArea", "stFileUploader", "stExpander",
                "stMetricValue", "stVerticalBlockBorderWrapper",
                "stMainMenuPopover", "stMainMenuItem", "stHeader", "stToolbar",
                "stAppDeployButton", "block-container", "stHorizontalBlock",
                "stExpanderDetails", "stDialog", "stProgressBarTrack",
                "prefers-reduced-motion"):
        assert sel in css, sel


def test_expander_and_option_hover_states_present():
    css = css_for()
    for sel in ('stExpander"] summary:hover',
                'stExpander"] summary:hover p',
                'stExpander"] summary:hover svg',
                'stExpander"] summary:focus-visible',
                'stExpander"] summary:active',
                'stExpander"] details[open] > summary',
                'stSelectbox"] > div:hover',
                'stSelectbox"] > div:focus-within',
                'stSelectbox"] input[role="combobox"]',
                'stSelectbox"]:focus-within button svg',
                'stRadioOption"]:hover',
                'stRadioOption"]:hover p',
                'stRadioOption"]:focus-within',
                'stCheckbox"]:hover',
                'stCheckbox"]:hover p',
                'stCheckbox"]:focus-within',
                'stMainMenuItem"]:hover span',
                'stMainMenuItem"]:hover p',
                'role="option"]:hover p',
                '.stApp a:hover'):
        assert sel in css, sel


def test_input_and_uploader_focus_states_present():
    css = css_for()
    for sel in ('stTextInput"] input:focus-visible',
                'stTextArea"] textarea:focus-visible',
                'stFileUploader"] button:focus-visible',
                'stFileUploader"] button:active',
                'stFileUploader"] button:disabled',
                'stProgressBarTrack"] > div'):
        assert sel in css, sel


def test_alerts_have_comfortable_padding_and_no_accent_bar():
    css = css_for()
    assert "padding: 20px 24px" in css
    assert "border-left" not in css
    assert "stAlertContent" not in css


def test_responsive_and_spacing_scale_present():
    css = css_for()
    assert "@media (max-width: 640px)" in css
    assert "flex-wrap: wrap" in css
    assert "min-height: 2.75rem" in css
    for var in ("--sp-1", "--sp-4", "--sp-6", "--r-md", "--r-lg"):
        assert var in css
    assert "word-break: normal" in css


def test_expander_header_surface_stable_all_states():
    css = re.sub(r"/\*.*?\*/", "", css_for(), flags=re.S)
    # Retired dead selectors must stay out (proven against 1.66.1 bundle).
    assert 'stExpander"] > div > :first-child' not in css
    assert "data-baseweb" not in css
    blocks = re.findall(r"([^{}]*stExpander[^{}]*summary[^{}]*)\{([^{}]*)}", css)
    assert len(blocks) >= 3, len(blocks)
    for sel, body in blocks:
        assert "var(--pruv-hover)" not in body, sel  # no bg wash
        assert re.search(r"#[0-9A-Fa-f]{6}", body) is None, sel
        if "background:" not in body:
            continue  # focus-ring-only rule
        nested = any(tag in sel for tag in (" span", " p", " div", " svg"))
        if nested:
            assert "background: transparent" in body, sel
        else:
            assert "background: var(--pruv-cards)" in body, sel
            assert "color: var(--pruv-text)" in body, sel


def test_dropdown_trigger_surface_stable_all_states():
    css = re.sub(r"/\*.*?\*/", "", css_for(), flags=re.S)
    for sel in ('[role="listbox"]', '[role="option"]',
                '[role="option"]:hover',
                '[role="option"][aria-selected="true"]'):
        assert sel in css, sel
    # The old per-widget saved-selector override is gone with dark mode.
    assert "open_pick" not in css
    assert "saved-select" not in css
    blocks = re.findall(r"([^{}]*stSelectbox[^{}]*)\{([^{}]*)}", css)
    assert len(blocks) >= 4, len(blocks)
    for sel, body in blocks:
        assert "var(--pruv-hover)" not in body, sel  # no bg wash
        assert re.search(r"#[0-9A-Fa-f]{6}", body) is None, sel
        if "background:" in body:
            assert ("background: var(--pruv-input)" in body
                    or "background: transparent" in body), sel
    popup = re.findall(r"([^{}]*\[role=\"(?:listbox|option)\"[^{}]*)\{([^{}]*)}", css)
    assert popup
    for sel, body in popup:
        assert re.search(r"#[0-9A-Fa-f]{6}", body) is None, sel


def test_link_buttons_share_button_styling():
    css = css_for()
    for sel in ('stLinkButton"] a {', 'stLinkButton"] a:hover',
                'stLinkButton"] a:focus-visible', 'stLinkButton"] a:active',
                'stLinkButton"] a[aria-disabled="true"]',
                'stLinkButton"] a:hover span', 'stLinkButton"] a span'):
        assert sel in css, sel


def test_button_selectors_use_descendants_not_direct_children():
    # Controls render through wrapper layers, so `testid > control` misses.
    css = css_for()
    assert '"] > button' not in css
    assert '"] > a' not in css
    for sel in ('stButton"] button,', 'stDownloadButton"] button,',
                'stPopoverButton"] button {',
                'stPopoverButton"] button:hover',
                'stPopoverButton"] button:focus-visible',
                'stPopoverButton"] button:active',
                'stPopoverButton"] button:disabled',
                'stPopoverButton"] button svg'):
        assert sel in css, sel


def test_links_have_underline_and_states():
    css = css_for()
    assert ".stApp a { color: var(--pruv-accent); text-decoration: underline; }" in css
    assert ".stApp a:visited" in css
    assert 'a[target="_blank"]::after' in css


def test_dashboard_cards_equal_height_structure():
    row = ('[data-testid="stHorizontalBlock"]'
           ':has(.st-key-go_req, .st-key-go_cus)')
    css = css_for()
    assert (row + " > [data-testid=\"column\"] > "
            "[data-testid=\"stVerticalBlockBorderWrapper\"] {") in css
    assert row + ' [data-testid="stVerticalBlock"] {' in css
    assert "margin-top: auto" in css
    assert ("[data-testid=\"stVerticalBlockBorderWrapper\"] {\n"
            "  border-color: var(--pruv-border); border-radius: var(--r-md);") in css


def test_content_width_contained():
    assert "max-width: 72rem" in css_for()


def test_selectbox_trigger_controls_full_surface():
    css = css_for()
    sel = '[data-testid="stSelectbox"] div:has(> input)'
    for fragment in (sel + " {", sel + ":hover", sel + ":focus-within",
                     sel + " > input", sel + " input::placeholder",
                     sel + " span", sel + " button svg"):
        assert fragment in css, fragment


def test_dashboard_breakpoints_responsive_grid():
    css = css_for()
    row = ('[data-testid="stHorizontalBlock"]'
           ':has(.st-key-go_req, .st-key-go_cus)')
    assert "@media (max-width: 700px)" in css
    assert row in css
    assert "flex: 1 1 100%" in css
    assert "max-width: 1500px" not in css
    assert "max-width: 900px" not in css
    assert "nth-child(4)" not in css
    assert "text-wrap: balance" in css


def test_micro_motion_respects_reduced_motion():
    css = css_for()
    assert "transition: background-color 120ms ease" in css
    reduced_at = css.index("prefers-reduced-motion")
    assert '[role="option"]' in css[reduced_at:]


def test_print_block_forces_readable_report():
    css = css_for()
    assert "@media print" in css
    printed = css[css.index("@media print"):]
    for sel in ('stSidebar"]', 'stHeader"]', 'stToolbar"]', 'stButton"]',
                'stDownloadButton"]', 'stLinkButton"]', 'stPopoverButton"]',
                'stFileUploader"]', 'stRadio"]', 'stSelectbox"]',
                'stTextInput"]', 'stTextArea"]'):
        assert sel in printed, sel
    assert "background: #FFFFFF !important" in printed
    assert "color: #1A1A1A !important" in printed
    assert "break-inside: avoid" in printed
    assert "details > :not(summary)" in printed

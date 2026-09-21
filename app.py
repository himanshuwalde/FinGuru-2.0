# hello
import streamlit.components.v1 as components
import pages.profile as profile
import pages.add_transaction as add_transaction
import pages.dashboard as dashboard
import pages.account_aggregator as account_aggregator
import pages.tax_planner as tax_planner
import pages.ai_advisor as ai_advisor
import streamlit as st
from supabase import create_client, Client
from utils.user_settings import ensure_user_settings

st.set_page_config(page_title="AI Financial Guru", page_icon="💰", layout="wide")

# ==========================================
# ✨ SUPABASE PASSWORD-RESET HANDOFF
# Supabase's implicit-flow reset email delivers its one-time tokens in the URL
# *fragment* (#access_token=...&refresh_token=...&type=recovery). Server-side
# Python can never see a fragment, and a <script> inside components.html cannot
# redirect the app either: on Streamlit Cloud the component iframe is sandboxed
# WITHOUT allow-top-navigation, so window.parent.location.replace() throws a
# SecurityError (verified against the live deployment). We therefore read the
# fragment inside a small custom component (recovery_reader/) and hand the
# tokens back to Python through the component's return value — no navigation.
# ==========================================
import os as _os
import json
_RECOVERY_READER_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "recovery_reader")
_recovery_reader = components.declare_component("recovery_reader", path=_RECOVERY_READER_DIR)


# ==========================================
# ✨ AUTH AUTOFILL ENHANCER
# Streamlit renders st.text_input as standalone widgets with autocomplete="off"
# and no name/association, so browsers refuse to treat Email+Password as a
# login form. Two problems are solved here:
#
#  1. SILENT INSTANT FILL — if the inputs are marked as a login form at page
#     load, Chrome fills the saved password immediately, while Streamlit's
#     controlled React input is wiped back to "" on its next re-render, so the
#     fields LOOK filled but submit empty credentials ("Login failed" with the
#     right password). To avoid that we apply the form recognition LAZILY —
#     only when the user's focus/click reaches an auth field. Chrome (and other
#     managers) then surface their account chooser on click instead of filling
#     silently, and the chosen credential lands at a stable moment.
#
#  2. FILLED-VALUE PROPAGATION — when a password manager does write into the
#     inputs, the value does not always reach Streamlit's state. A companion
#     component (auth_autofill_reader/) echoes the live DOM values back to
#     Python each render, and the app adopts them into session_state so a
#     submit uses real credentials. (See _autofill_echo below.)
#
# __AUTH_MODE__ is substituted per render.
# ==========================================
_AUTH_AUTOFILL_SCRIPT = """
<script>
(function() {
    var MODE = "__AUTH_MODE__";
    var FORM_ID = "st_auth_autofill_form";
    var wired = false;
    var WIRE_SELECTOR = (MODE === "update_pwd")
        ? 'input[type="password"]'
        : 'input[aria-label="Email"], input[aria-label="Password"]';

    function wire() {
        var doc;
        try { doc = window.parent.document; } catch (e) { return; }
        var email = doc.querySelector('input[aria-label="Email"]');
        var pwd = doc.querySelector('input[type="password"]');
        if (MODE === "update_pwd") {
            if (!pwd) return;
        } else if (!email && !pwd) {
            return;
        }
        if (wired) return;
        wired = true;

        // One hidden native form the fields are ASSOCIATED with (form= attr), so
        // browsers see a single credential form — without touching Streamlit's DOM.
        var form = doc.getElementById(FORM_ID);
        if (!form) {
            form = doc.createElement("form");
            form.id = FORM_ID;
            form.setAttribute("aria-hidden", "true");
            form.style.cssText = "position:absolute;left:-9999px;top:-9999px;width:0;height:0;overflow:hidden;";
            var sb = doc.createElement("button");
            sb.type = "submit";
            sb.setAttribute("tabindex", "-1");
            sb.style.cssText = "display:none;";
            form.appendChild(sb);
            doc.body.appendChild(form);
        }

        function apply(field, name, auto) {
            if (!field) return;
            field.setAttribute("form", FORM_ID);
            field.setAttribute("name", name);
            field.setAttribute("autocomplete", auto);
        }
        if (email) apply(email, "email", (MODE === "signup" || MODE === "reset") ? "email" : "username");
        if (pwd) apply(pwd, "password", MODE === "login" ? "current-password" : "new-password");

        // Enter inside an auth field should submit the mode's action.
        if (!form.dataset.stAutoReady) {
            form.dataset.stAutoReady = "1";
            form.addEventListener("submit", function (ev) {
                ev.preventDefault();
                var btn = doc.querySelector('button[kind="primaryFormSubmit"], button[kind="primary"]');
                if (btn) btn.click();
            });
        }
    }

    // Lazy recognition: hook the parent document and enable the fields only when
    // the user actually interacts with the auth area (focus/click dispatch first,
    // before the browser decides whether to show its credential chooser/fill).
    function enable() { wire(); }

    var doc = null;
    try { doc = window.parent.document; } catch (e) {}
    if (doc) {
        doc.addEventListener("focus", enable, true);
        doc.addEventListener("click", enable, true);

        // Attach one-time hooks to the inputs as they appear, so focus/click on a
        // specific field still enables recognition even after a re-render. This
        // only ADDS listeners — wire() stays lazy (focus/click only).
        function attachLazily() {
            var items = [];
            try { items = [].slice.call(doc.querySelectorAll(WIRE_SELECTOR)); } catch (e) {}
            items.forEach(function (el) {
                if (el.dataset.stAutoHooked) return;
                el.dataset.stAutoHooked = "1";
                el.addEventListener("focus", enable, true);
                el.addEventListener("click", enable, true);
            });
        }
        if (doc.readyState !== "loading") attachLazily();
        else doc.addEventListener("DOMContentLoaded", attachLazily);
        setInterval(attachLazily, 1000);
    }
})();
</script>
"""

# ==========================================
# ✨ AUTH AUTOFILL VALUE ECHO
# Companion to _AUTH_AUTOFILL_SCRIPT: a small custom component captures the live
# email/password values the inputs hold (memory that React can't wipe) and
# reports them to Python on every render, so the app can adopt browser-filled
# values into session_state before building the widgets.
# ==========================================
_AUTOFILL_READER_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "auth_autofill_reader")
_autofill_reader = components.declare_component("auth_autofill_reader", path=_AUTOFILL_READER_DIR)

# Widget keys per auth mode: (email_key_or_None, password_key_or_None)
_AUTOFILL_KEYS = {
    "login": ("login_email", "login_password"),
    "signup": ("signup_email", "signup_password"),
    "reset": ("reset_email_input", None),
    "update_pwd": (None, "new_pwd_input"),
}

# ==========================================
# ✨ SESSION PERSISTENCE ACROSS REFRESH
# Streamlit's session_state is rebuilt on every page refresh, so a refresh drops
# the login and strands the user on the landing page. To keep a logged-in user
# logged in through a refresh (no re-authentication), the app persists a small
# copy of the Supabase auth session in the browser via the session_keep/
# component and re-arms it at the top of each run. The user's NAV choice is NOT
# persisted — every fresh load starts on the landing page (Dashboard):
#
#   * cookie (fast path)   — session_keep writes `finguru_session` to a
#     same-origin cookie (path=/); the browser sends it with the refresh request
#     and Python reads it straight out of the request headers on the very FIRST
#     run — the session is restored before routing, so refresh goes straight to
#     the app page with no landing-page flash and no re-login.
#
#   * localStorage (fallback) — session_keep mirrors the blob into localStorage
#     and posts it back on the following rerun, so refresh-survival still works if
#     the cookie header is stripped by a proxy/cloud cache (in that case the
#     first run briefly shows the landing page before re-routing).
#
# Security: storing an OAuth access/refresh token in the browser is exactly what
# Supabase's own JS client does for every SPA (its default storage is
# localStorage). The cookie is SameSite=Lax (blocks cross-site carries) and
# Secure on https. Tokens never enter the URL or server-side logs.
# ==========================================
_SESSION_KEEP_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "session_keep")
_session_keep = components.declare_component("session_keep", path=_SESSION_KEEP_DIR)
_SESSION_COOKIE_NAME = "finguru_session"
_DEFAULT_PAGE = "📊 Dashboard"


def _autofill_echo(mode):
    """Adopt browser-filled auth values into Streamlit state.

    Password managers write directly into the visible <input>; Streamlit's
    controlled widget sometimes never learns the new value and, worse, wipes the
    field back to "" on its next re-render — so a submit silently sends empty
    credentials even though the fields looked filled (this was the reported
    "can't log in with correct credentials"). The auth_autofill_reader component
    captures the live input values (memory React can't wipe) and reports them
    here on every render; we adopt them into session_state BEFORE the widgets
    are created, so the widgets render with the real values and the submit uses
    them. On normal typing this adoption is a no-op (values already match).
    """
    key = _AUTOFILL_KEYS.get(mode)
    if not key:
        return
    email_key, pwd_key = key
    try:
        v = _autofill_reader() or {}
    except Exception:
        return
    if not v or v.get("error"):
        return
    # Adopt non-empty values observed in the inputs. During normal typing this
    # is a no-op (the value already matches), and for a password-manager fill it
    # is exactly what makes the submit use real credentials.
    if email_key and v.get("email"):
        st.session_state[email_key] = v["email"]
    if pwd_key and v.get("password"):
        st.session_state[pwd_key] = v["password"]

# ==========================================
# ✨ SIDEBAR THEME FIX
# Strategy: Inject a <style> tag directly into the PARENT document
# from a components.html iframe. This bypasses the iframe sandbox
# for stylesheets and correctly applies to Streamlit's sidebar DOM.
# We detect the theme by reading the actual computed background color
# of the app container — not the OS preference — so it always matches
# whatever theme Streamlit is currently using.
# ==========================================
components.html("""
<script>
(function() {
    function applyTheme() {
        try {
            const doc = window.parent.document;

            // -- 1. Detect current Streamlit theme --
            const appBg = doc.querySelector('[data-testid="stAppViewContainer"]');
            if (!appBg) return;
            const bgColor = window.parent.getComputedStyle(appBg).backgroundColor;
            const rgb = bgColor.match(/\d+/g);
            if (!rgb) return;
            const brightness = (parseInt(rgb[0]) * 299 + parseInt(rgb[1]) * 587 + parseInt(rgb[2]) * 114) / 1000;
            const isDark = brightness < 128;

            // -- 2. Define exact colors for each theme --
            // These match Streamlit's own default theme values exactly
            const sidebarBg   = isDark ? '#0e1117' : '#f0f2f6';
            const textColor   = isDark ? '#fafafa' : '#31333f';
            const subText     = isDark ? 'rgba(250,250,250,0.6)' : 'rgba(49,51,63,0.6)';
            const borderColor = isDark ? 'rgba(250,250,250,0.1)' : 'rgba(49,51,63,0.1)';
            const hoverBg     = isDark ? 'rgba(250,250,250,0.05)' : 'rgba(49,51,63,0.05)';

            // -- 3. Remove any previously injected style to avoid duplicates --
            const existing = doc.getElementById('finguru-sidebar-fix');
            if (existing) existing.remove();

            // -- 4. Build and inject a <style> tag into the PARENT document <head> --
            const style = doc.createElement('style');
            style.id = 'finguru-sidebar-fix';
            style.textContent = `
                /* === FINGURU SIDEBAR FIX === */

                /* Target all structural wrappers of the sidebar */
                [data-testid="stSidebar"],
                [data-testid="stSidebar"] > div,
                [data-testid="stSidebar"] > div > div,
                [data-testid="stSidebar"] > div > div > div,
                section[data-testid="stSidebar"],
                section[data-testid="stSidebar"] > div {
                    background-color: ${sidebarBg} !important;
                    backdrop-filter: none !important;
                    -webkit-backdrop-filter: none !important;
                }

                /* Sidebar text colors */
                [data-testid="stSidebar"] p,
                [data-testid="stSidebar"] span,
                [data-testid="stSidebar"] label,
                [data-testid="stSidebar"] div {
                    color: ${textColor};
                }

                /* Radio button labels - Main Menu */
                [data-testid="stSidebar"] [role="radiogroup"] label,
                [data-testid="stSidebar"] [role="radiogroup"] label div,
                [data-testid="stSidebar"] [role="radiogroup"] label span {
                    color: ${textColor} !important;
                }
                [data-testid="stSidebar"] [role="radiogroup"] label {
                    border-radius: 8px;
                    padding: 8px 12px;
                    background-color: transparent;
                }
                [data-testid="stSidebar"] [role="radiogroup"] label:hover {
                    background-color: ${hoverBg} !important;
                }
                [data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"] {
                    background-color: ${hoverBg} !important;
                }
                [data-testid="stSidebar"] [role="radiogroup"] {
                    background-color: transparent !important;
                }

                /* HR dividers */
                [data-testid="stSidebar"] hr {
                    border-color: ${borderColor} !important;
                }

                /* Log Out button */
                [data-testid="stSidebar"] button {
                    color: ${textColor} !important;
                    border-color: ${borderColor} !important;
                }

                /* Mobile-only: full height coverage */
                @media (max-width: 767px) {
                    [data-testid="stSidebar"],
                    [data-testid="stSidebar"] > div,
                    section[data-testid="stSidebar"] {
                        min-height: 100vh !important;
                        min-height: 100dvh !important;
                    }
                }
            `;
            doc.head.appendChild(style);

        } catch(e) {
            console.warn('FinGuru sidebar fix error:', e);
        }
    }

    // Run immediately, then keep polling to handle:
    // - Streamlit rerenders
    // - Mobile sidebar slide-open animation
    // - Theme toggle by user
    applyTheme();
    setInterval(applyTheme, 500);
})();
</script>
""", height=0)

# ==========================================
# ✨ MAIN CSS
# ==========================================
st.markdown("""
<style>
    /* ===========================
       DESIGN SYSTEM — FinGuru
       Calm, dense, professional.
       One accent color. Tight type. Flat cards.
       =========================== */

    /* --- Typography --- */
    .gradient-text {
        color: var(--text-color);
        font-size: 2.4rem;
        font-weight: 700;
        text-align: center;
        padding-bottom: 0.5rem;
        margin-bottom: 0;
        display: inline-block;
        letter-spacing: -0.5px;
    }
    .sub-text {
        font-size: 0.95rem;
        color: var(--text-color);
        opacity: 0.6;
        text-align: center;
        margin-top: 0;
        margin-bottom: 2rem;
        max-width: 600px;
        margin-left: auto;
        margin-right: auto;
        line-height: 1.6;
    }

    /* --- Alerts --- */
    div[data-testid="stAlert"] {
        border-radius: 8px;
        padding: 1rem 1.25rem;
        border: 1px solid rgba(150, 150, 150, 0.15);
        background-color: var(--secondary-background-color);
    }

    /* --- Metric cards --- */
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color);
        border-radius: 8px;
        padding: 1rem 0.75rem;
        text-align: center;
        border: 1px solid rgba(150, 150, 150, 0.12);
    }
    div[data-testid="stMetricValue"], div[data-testid="stMetricLabel"] {
        justify-content: center;
    }

    /* --- Sidebar --- */
    @media (min-width: 768px) {
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color) !important;
            border-right: 1px solid rgba(150, 150, 150, 0.15) !important;
            min-width: 260px !important;
        }
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label {
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 2px;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
        background-color: var(--background-color);
    }
    [data-testid="stSidebar"] hr {
        margin-top: 0.75rem;
        margin-bottom: 0.75rem;
        border-top-color: rgba(150, 150, 150, 0.15);
    }

    /* --- Sidebar section label --- */
    .sidebar-section-label {
        font-size: 0.68rem;
        color: var(--text-color);
        opacity: 0.45;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 6px;
        padding-left: 2px;
    }

    /* --- Feature Card (landing page) --- */
    .feature-card {
        background-color: var(--secondary-background-color);
        border: 1px solid rgba(150, 150, 150, 0.12);
        border-radius: 8px;
        padding: 1.25rem;
        margin-bottom: 0.75rem;
        height: 100%;
    }
    .feature-title {
        font-weight: 600;
        font-size: 0.95rem;
        color: var(--text-color);
        margin-bottom: 0.35rem;
    }
    .feature-desc {
        color: var(--text-color);
        opacity: 0.6;
        font-size: 0.82rem;
        line-height: 1.5;
    }

    /* ======== Landing page ======== */
    .landing-hero {
        text-align: center;
        padding: 2.5rem 1rem 1rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 100%;
    }
    .landing-eyebrow {
        display: inline-block; text-transform: uppercase; letter-spacing: 1.5px;
        font-size: 0.7rem; font-weight: 600; color: var(--primary-color);
        background: rgba(37,99,235,0.06);
        border: 1px solid rgba(37,99,235,0.15);
        padding: 5px 14px; border-radius: 999px; margin-bottom: 1rem;
    }
    .landing-hero h1 {
        font-size: 2.4rem; font-weight: 700; line-height: 1.15; margin-bottom: 1rem;
        letter-spacing: -0.5px;
        text-align: center;
        width: 100%;
        color: var(--text-color);
    }
    p.landing-sub,
    div[data-testid="stMarkdownContainer"] p.landing-sub {
        display: block !important;
        text-align: center !important;
        font-size: 0.95rem; color: var(--text-color); opacity: .6;
        width: 100% !important;
        max-width: 560px !important;
        margin: 0 auto 1.5rem auto !important;
        line-height: 1.65;
    }
    .hero-pills { display: flex; justify-content: center; flex-wrap: wrap; gap: 6px; margin-bottom: 1.5rem; width: 100%; }
    .hero-pill {
        font-size: .72rem; font-weight: 500; letter-spacing: .2px; padding: 4px 12px;
        border-radius: 999px; color: var(--text-color); opacity: 0.7;
        background: var(--secondary-background-color); border: 1px solid rgba(150,150,150,.15);
    }

    /* --- Section headers (landing) --- */
    .section-head { text-align: center; margin: 0.5rem 0 1.8rem; }
    .section-eyebrow {
        display: inline-block; text-transform: uppercase; letter-spacing: 2px;
        font-size: .68rem; font-weight: 600; color: var(--primary-color); margin-bottom: .5rem;
    }
    .section-head h2 { font-size: 1.3rem; font-weight: 700; color: var(--text-color); margin: .2rem 0 .4rem; letter-spacing: -0.3px; }
    .section-head p { max-width: 520px; margin: 0 auto; color: var(--text-color); opacity: .55; line-height: 1.55; font-size: .88rem; }

    /* --- Module cards (landing) --- */
    .module-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(150,150,150,.12); border-radius: 8px;
        padding: 1.1rem 1.1rem 1rem; height: 100%;
    }
    .module-icon {
        width: 36px; height: 36px; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.1rem; margin-bottom: .75rem;
    }
    .module-title { font-weight: 600; font-size: 0.9rem; color: var(--text-color); margin-bottom: .3rem; }
    .module-desc { color: var(--text-color); opacity: .6; font-size: .8rem; line-height: 1.5; }
    .module-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: .7rem; }
    .module-tag {
        font-size: .65rem; font-weight: 500; letter-spacing: .2px; padding: 2px 8px;
        border-radius: 999px; border: 1px solid rgba(150,150,150,.18); color: var(--text-color); opacity: .7;
    }

    /* --- Steps (landing) --- */
    .step { text-align: center; }
    .step-num {
        width: 40px; height: 40px; margin: 0 auto .65rem; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 1rem; color: #FFFFFF;
        background: var(--primary-color);
    }
    .step h4 { color: var(--text-color); margin: .15rem 0 .3rem; font-size: 0.9rem; font-weight: 600; }
    .step p { color: var(--text-color); opacity: .55; font-size: .82rem; line-height: 1.5; padding: 0 0.5rem; }

    /* --- Trust strip (landing) --- */
    .stack-strip {
        text-align: center; color: var(--text-color); opacity: .45;
        font-size: .72rem; letter-spacing: .5px; line-height: 2;
    }

    /* --- Trust badges (landing) --- */
    .trust-badges {
        display: flex; justify-content: center; flex-wrap: wrap; gap: 1rem;
        margin: 1.5rem 0;
    }
    .trust-badge {
        font-size: .75rem; font-weight: 500; color: var(--text-color); opacity: 0.6;
        display: flex; align-items: center; gap: 0.35rem;
    }

    /* --- Page section header (inside modules) --- */
    .page-header {
        margin-bottom: 1.25rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid rgba(150, 150, 150, 0.12);
    }
    .page-header h2 {
        font-size: 1.15rem;
        font-weight: 600;
        color: var(--text-color);
        margin: 0;
        letter-spacing: -0.2px;
    }
    .page-header p {
        font-size: 0.8rem;
        color: var(--text-color);
        opacity: 0.5;
        margin: 0.2rem 0 0 0;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_email' not in st.session_state: st.session_state.user_email = ""
if 'user_id' not in st.session_state: st.session_state.user_id = ""
if 'show_auth_page' not in st.session_state: st.session_state.show_auth_page = False 
if 'editing_account' not in st.session_state: st.session_state.editing_account = None 
if 'force_page' not in st.session_state: st.session_state.force_page = None
if 'ai_consent' not in st.session_state: st.session_state.ai_consent = False
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = 'login'
if '_auth_access' not in st.session_state: st.session_state._auth_access = ""
if '_auth_refresh' not in st.session_state: st.session_state._auth_refresh = ""


def _read_session_cookie():
    """Read the persisted FinGuru session out of the request's Cookie header.
    This is synchronous — it is available on the very first run after a refresh,
    which is what lets us restore before routing (no landing-page flash)."""
    try:
        import urllib.parse
        headers = st.context.headers
    except Exception:
        return None
    for k, v in headers.items():
        if str(k).lower() != "cookie":
            continue
        for part in v.split(";"):
            part = part.strip()
            if part.startswith(_SESSION_COOKIE_NAME + "="):
                raw = part[len(_SESSION_COOKIE_NAME) + 1:]
                try:
                    return json.loads(urllib.parse.unquote(raw))
                except Exception:
                    return None
    return None


def _persist_json():
    """Serialize the live login + current nav choice into the JSON blob the
    browser keeps (cookie + localStorage mirror). None when not logged in.
    The "page" field survives so a same-tab REFRESH resumes the module the user
    was on; a genuinely fresh visit (reopened app) is corrected to the landing
    page separately using the browser's reported navigation type. See the
    fresh-visit correction in the restore block below."""
    state = st.session_state
    if not state.get("logged_in") or not state.get("_auth_access"):
        return None
    return json.dumps({
        "access_token": state["_auth_access"],
        "refresh_token": state.get("_auth_refresh") or "",
        "email": state.get("user_email") or "",
        "id": state.get("user_id") or "",
        "page": state.get("sidebar_choice", _DEFAULT_PAGE),
    })


def _restore_session_from(blob):
    """Re-arm the Supabase client and rebuild login state from a persisted
    {access_token, refresh_token, email, id, page} blob so a page refresh stays
    logged in and resumes the module the user was on. The page restore is
    PROVISIONAL — a genuinely fresh visit (app reopened after closing) is
    corrected to the landing page later in the restore block.
    Returns True when the session was restored."""
    if not blob or not blob.get("access_token"):
        return False
    try:
        # set_session needs both tokens to be able to replay refresh-based
        # expiry; then get_user() confirms the tokens still sign the user.
        supabase.auth.set_session(blob["access_token"], blob.get("refresh_token") or "")
        supabase.auth.get_user()
    except Exception:
        try:  # the access token may have already expired — let the refresh try
            refreshed = supabase.auth.refresh_session()
            sess = getattr(refreshed, "session", None)
            user = getattr(refreshed, "user", None)
            if not refreshed or not user or not sess:
                return False
            blob = dict(blob)
            blob["access_token"] = getattr(sess, "access_token", "") or ""
            blob["refresh_token"] = getattr(sess, "refresh_token", "") or ""
            blob["email"] = getattr(user, "email", "") or ""
            blob["id"] = getattr(user, "id", "") or ""
        except Exception:
            return False
    st.session_state.logged_in = True
    st.session_state.user_email = blob.get("email") or ""
    st.session_state.user_id = blob.get("id") or ""
    st.session_state.show_auth_page = False
    st.session_state["_auth_access"] = blob.get("access_token") or ""
    st.session_state["_auth_refresh"] = blob.get("refresh_token") or ""
    if blob.get("page"):
        st.session_state.sidebar_choice = blob["page"]
    return True

def _app_base_url():
    """Best-effort base URL of the app, used as the password-reset redirect so
    emailed links open on the real host instead of a hardcoded localhost."""
    try:
        headers = st.context.headers
        host = None
        for k, v in headers.items():  # case varies across proxies
            if k.lower() == "host":
                host = v
                break
        if not host:
            return None
        scheme = "https"
        for k, v in headers.items():
            if k.lower() == "x-forwarded-proto" and "https" not in v.lower():
                scheme = "http"
                break
        if host.split(":")[0] in ("localhost", "127.0.0.1"):
            scheme = "http"
        return f"{scheme}://{host}"
    except Exception:
        return None


def _consume_recovery_params():
    """If the URL carries a Supabase password-reset handoff, exchange it for a
    real auth session so the New-Password form can update the password.

    Handled link shapes:
      * implicit flow — `access_token`/`refresh_token` delivered by the
        recovery_reader component (read from the URL fragment);
      * PKCE flow    — a one-time `code` in the query string;
      * legacy       — a `token_hash` + `type` pair.

    On success the one-time tokens are scrubbed from the URL and True is
    returned so the caller renders the reset form. Returns False otherwise.
    """
    qp = st.query_params
    is_recovery = bool(qp.get("recovery")) or str(qp.get("type", "")).lower() == "recovery"
    if not is_recovery:
        # The app only signs in with email+password, so a bare PKCE `code`
        # can only come from a Supabase confirm link (recovery in this case).
        is_recovery = bool(qp.get("code"))

    if not is_recovery:
        return False

    if not (qp.get("access_token") or qp.get("code") or qp.get("token_hash")):
        # A recovery marker with no forwarded tokens = old/dead link.
        st.query_params.clear()
        st.session_state.show_auth_page = True
        st.session_state.auth_mode = 'login'
        st.error("This password-reset link is invalid or has expired. Please request a new one.")
        return False

    try:
        if qp.get("access_token"):
            supabase.auth.set_session(qp["access_token"], qp.get("refresh_token", "") or "")
        elif qp.get("code"):
            supabase.auth.exchange_code_for_session({"auth_code": qp["code"]})
        elif qp.get("token_hash"):
            supabase.auth.verify_otp({"token_hash": qp["token_hash"], "type": "recovery"})

        if supabase.auth.get_session():
            # Scrub the temporary tokens from the address bar now that they're used.
            st.query_params.clear()
            st.session_state.show_auth_page = True
            st.session_state.auth_mode = 'update_pwd'
            return True
    except Exception:
        st.query_params.clear()
        st.session_state.show_auth_page = True
        st.session_state.auth_mode = 'login'
        st.error("This password-reset link is invalid or has expired. Please request a new one.")
        return False
    return False


def _fold_fragment_into_query():
    """Read any password-reset tokens out of the URL fragment via the
    recovery_reader component and merge them into st.query_params so
    _consume_recovery_params() can establish the session and show the
    New-Password form. Returns True if recovery tokens were folded in.

    The component only sees the fragment after the page loads, so its value is
    first available on the *second* script run — a normal component callback —
    and the session exchange happens on that rerun.
    """
    if st.session_state.get("_recovery_handled"):
        return False
    try:
        value = _recovery_reader()
    except Exception:
        value = None
    if not value or not value.get("recovery"):
        return False
    try:
        import urllib.parse
        tokens = urllib.parse.parse_qs(str(value["recovery"]).lstrip("#"))
        for key, vals in tokens.items():
            if vals:
                st.query_params[key] = vals[0]
        if "recovery" not in {str(k) for k in st.query_params}:
            st.query_params["recovery"] = "1"
    except Exception:
        return False
    return True


_recovery_folded = _fold_fragment_into_query()
_recovery_consumed = _consume_recovery_params()
if _recovery_folded or _recovery_consumed:
    # The one-time tokens were seen (valid or not) — never re-process them.
    st.session_state["_recovery_handled"] = True

# ==========================================
# ✨ RESTORE SESSION ON LOAD / PERSIST ON NAV
# Runs before the routing branches. Rebuilds a logged-in session from the
# browser-persisted blob (see session_keep/ above) so a page refresh keeps the
# user logged in on the same module. Skipped while a password-reset handoff is
# in flight (that flow must land on the New-Password form) and right after
# Log Out (the persisted copy is being erased that same run).
# ==========================================
_persist_clear_requested = bool(st.session_state.pop("_persist_clear", False))

if (not (_recovery_folded or _recovery_consumed)
        and not _persist_clear_requested
        and not st.session_state.logged_in):
    try:
        _cookie_blob = _read_session_cookie()
    except Exception:
        _cookie_blob = None
    if _cookie_blob and not _restore_session_from(_cookie_blob):
        # Stale/invalid tokens — retire them so every refresh stops retrying.
        _persist_clear_requested = True
        st.error("Your session expired. Please log in again.")

# Browser bridge — READ what the browser still holds: the persisted login blob
# plus (from the component's JS) HOW this document was loaded. The write-back
# happens at the END of the script, after routing, so the page actually stored
# is the one the user is looking at — a fresh visit redirected to the landing
# page writes the landing page in the same run, so a stale "last module" never
# survives a full app reopen.
try:
    _keeper = _session_keep() or {}
except Exception:
    _keeper = {}

if (not st.session_state.logged_in
        and not _persist_clear_requested
        and not (_recovery_folded or _recovery_consumed)
        and _keeper.get("session")
        # localStorage survives browser restarts (the session cookie does not),
        # so it must only ever be trusted on a same-tab RELOAD — never on a
        # fresh visit, where the user has to re-authenticate. Without this gate
        # a reopened app would silently resurrect the old session from the
        # localStorage mirror and skip the landing page again.
        and (_keeper.get("navType") in ("reload", "back_forward"))):
    # Cookie was unavailable but the localStorage mirror survived — restore from
    # it; the end-of-script write re-creates the cookie too.
    _restore_session_from(_keeper["session"])

# ── Fresh visit vs refresh ─────────────────────────────────────────────────
# The browser reports how this document was loaded: "reload" (F5 / Ctrl+R) vs
# "navigate" (typed URL / app reopened after closing). A REFRESH keeps the
# logged-in session and the page the user was on. A genuinely FRESH visit (the
# app was closed and reopened, or the address was typed in a new tab) must NOT
# silently re-authenticate and drop the user onto a module — it starts over from
# the landing page and requires authentication again. This correction runs
# before the sidebar radio renders, so the landing page is what actually shows.
_nav_kind = (_keeper or {}).get("navType")
if (not st.session_state.get("_fresh_nav_corrected")
        and _nav_kind and _nav_kind not in ("reload", "back_forward")
        and st.session_state.logged_in):
    # Force re-authentication: clear the whole auth state so the landing page
    # (not the Dashboard) is what a fresh visit shows. This is the key part the
    # old code got wrong — it only reset sidebar_choice to the Dashboard, which
    # kept the restored session alive, skipped the landing + login form, and
    # then wrote "Dashboard" back to the persisted blob, poisoning every later
    # refresh into also landing on the Dashboard.
    for key in ['logged_in', 'user_email', 'user_id', 'show_auth_page',
                'editing_account', 'force_page', 'ai_consent',
                'aa_consent_token', 'has_synced_this_session']:
        st.session_state[key] = False if key in ['logged_in', 'show_auth_page', 'ai_consent', 'aa_consent_token', 'has_synced_this_session'] else ("" if key in ['user_email', 'user_id'] else None)
    st.session_state["_auth_access"] = ""
    st.session_state["_auth_refresh"] = ""
    st.session_state.auth_mode = "login"
    st.session_state.sidebar_choice = _DEFAULT_PAGE
    st.session_state["_fresh_nav_corrected"] = True
    # Wipe the persisted cookie + localStorage mirror this run, and make the
    # NEXT run skip the restore block too, so the stale blob can never log the
    # user back in.
    _persist_clear_requested = True
    st.session_state._persist_clear = True

def go_to_auth():
    st.session_state.show_auth_page = True

def go_back_home():
    st.session_state.show_auth_page = False

def render_module_grid(modules, per_row=3):
    """Render module cards in rows of `per_row`. If the last row has fewer
    cards than `per_row`, add equal spacer columns on both sides so the
    partial row stays centered instead of hugging the left edge."""
    for i in range(0, len(modules), per_row):
        row_items = modules[i:i + per_row]
        n = len(row_items)
        if n == per_row:
            cols = list(st.columns(per_row))
        else:
            spacer = (per_row - n) / 2
            cols = list(st.columns([spacer] + [1] * n + [spacer]))[1:-1]
        for card_col, (emoji, title, desc, tags) in zip(cols, row_items):
            tag_html = "".join(f'<span class="module-tag">{t}</span>' for t in tags)
            with card_col:
                st.markdown(f"""
                <div class="module-card">
                    <div class="module-icon" style="background: var(--secondary-background-color); border: 1px solid rgba(150,150,150,0.15);">{emoji}</div>
                    <div class="module-title">{title}</div>
                    <div class="module-desc">{desc}</div>
                    <div class="module-tags">{tag_html}</div>
                </div>
                """, unsafe_allow_html=True)

@st.dialog("Log out")
def confirm_logout():
    """Ask before signing out — log out is a destructive session action."""
    st.warning("Are you sure you want to log out?")
    c1, c2 = st.columns(2)
    if c1.button("Log out", type="primary", use_container_width=True):
        supabase.auth.sign_out()
        for key in ['logged_in', 'user_email', 'user_id', 'show_auth_page', 'editing_account', 'force_page', 'ai_consent', 'aa_consent_token', 'has_synced_this_session']:
            st.session_state[key] = False if key in ['logged_in', 'show_auth_page', 'ai_consent', 'aa_consent_token', 'has_synced_this_session'] else ("" if key in ['user_email', 'user_id'] else None)
        st.session_state["_auth_access"] = ""
        st.session_state["_auth_refresh"] = ""
        # Erase the persisted cookie + localStorage mirror on the next run, and
        # don't let the restore block resurrect the session in the meantime.
        st.session_state._persist_clear = True
        st.rerun()
    if c2.button("Cancel", use_container_width=True):
        st.rerun()

if st.session_state.logged_in:
    # ==========================================
    # ✨ THE JPMC AUTO-SYNC BACKGROUND LISTENER
    # ==========================================
    account_aggregator.run_background_sync(supabase, st.session_state.user_id)

    # ==========================================
    # ✨ PREFERRED CURRENCY + AI PERSONA LOADER
    # Pulls preferred_currency, ai_tone, financial_phase and risk_tolerance
    # from profiles into session_state once per login, so every page and every
    # LLM prompt reads the user's chosen currency and persona. Missing columns
    # (pre-migration) degrade gracefully to the INR / Strict Accountant /
    # Building Wealth / Moderate defaults.
    # ==========================================
    ensure_user_settings(supabase, st.session_state.user_id)

    # ==========================================
    # ✨ SIDEBAR — Clean Professional Layout
    # ==========================================

    st.sidebar.markdown("""
        <div style="margin-bottom: 1rem;">
            <span style="font-size: 1.05rem; font-weight: 700; color: var(--text-color); letter-spacing: -0.3px;">FinGuru</span>
            <span style="font-size: 0.65rem; font-weight: 500; color: var(--primary-color); margin-left: 4px; vertical-align: super;">AI</span>
        </div>
    """, unsafe_allow_html=True)

    # Quick access to Profile & Settings at the top
    if st.sidebar.button("⚙️ Settings", use_container_width=True, key="quick_profile_settings_btn"):
        st.session_state.force_page = "⚙️ Profile & Settings"
        st.rerun()

    # Default to Dashboard if no page selected
    if "sidebar_choice" not in st.session_state:
        st.session_state.sidebar_choice = "📊 Dashboard"

    # User info — clean, no gradient
    st.sidebar.markdown(f"""
        <div style="padding: 8px 0; margin-bottom: 4px;">
            <div style="font-size: 0.78rem; color: var(--text-color); opacity: 0.55; font-weight: 500;">{st.session_state.user_email}</div>
        </div>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("<hr style='margin-top: 0; margin-bottom: 8px;'>", unsafe_allow_html=True)
    st.sidebar.markdown('<div class="sidebar-section-label">Menu</div>', unsafe_allow_html=True)

    menu_options = [
        "📊 Dashboard",
        "💳 Transactions & Budgeting",
        "📈 Wealth",
        "🧾 Tax Planner",
        "🎯 Goals & Protection",
        "👨‍👩‍👧 Family & Legacy",
        "🤖 AI CA Advisor",
    ]

    # Guard against a stale persisted choice (pre-2.0 module names in an old
    # cookie/localStorage blob) — an unmatched value would crash the radio.
    if st.session_state.sidebar_choice not in menu_options:
        st.session_state.sidebar_choice = _DEFAULT_PAGE

    def clear_force_page():
        st.session_state.force_page = None

    choice = st.sidebar.radio("Navigation", menu_options, key="sidebar_choice", on_change=clear_force_page, label_visibility="collapsed")
    
    # Auto-Close Sidebar on Mobile Click
    components.html("""
    <script>
        window.parent.document.addEventListener('click', function(event) {
            if (window.parent.innerWidth < 768) {
                let isSidebarClick = event.target.closest('[data-testid="stSidebar"] div[role="radiogroup"] label');
                if (isSidebarClick) {
                    setTimeout(() => {
                        let closeBtn = window.parent.document.querySelector('[data-testid="stSidebar"] button');
                        if (closeBtn) {
                            closeBtn.click();
                        } else {
                            window.parent.document.dispatchEvent(new KeyboardEvent('keydown', {'key': 'Escape'}));
                        }
                    }, 150);
                }
            }
        });
    </script>
    """, height=0)

    st.sidebar.markdown("<hr>", unsafe_allow_html=True)

    if st.sidebar.button("🚪 Log Out", use_container_width=True):
        confirm_logout()

    # ==========================================
    # ✨ THE PRIVACY GATEKEEPER
    # ==========================================
    ai_powered_tools = ["🎯 Goals & Protection", "🤖 AI CA Advisor"]

    if choice in ai_powered_tools and not st.session_state.ai_consent:
        st.title("🛡️ AI Privacy & Consent")
        with st.container(border=True):
            st.info("👋 **Your Privacy Matters**")
            st.markdown("""
            To provide personalized insights, our AI (Gemini) analyzes your:
            * **Transaction Categories** (e.g., Groceries, Health)
            * **Spending Amounts**
            * **Account Balances**
            
            **Important:** Your real-world identity (Email/Name) is never sent to the AI. We only send the numbers and categories. By opting in, you agree to this processing under the **DPDP Act 2023**.
            """)
            if st.button("✅ I Agree & Opt-in", type="primary", use_container_width=True):
                st.session_state.ai_consent = True
                st.rerun()
            def decline_consent():
                st.session_state.sidebar_choice = "📊 Dashboard"
            st.button("❌ No thanks, take me back", on_click=decline_consent)
        st.stop() 

    # --- ROUTING ---
    if st.session_state.force_page == "add_transaction":
        add_transaction.render_page(supabase)
    elif st.session_state.force_page == "⚙️ Profile & Settings":
        profile.render_page(supabase)
    else:
        if choice == "📊 Dashboard":
            dashboard.render_page(supabase)
        elif choice == "💳 Transactions & Budgeting":
            import pages.transactions_budgeting as tb
            tb.render_page(supabase)
        elif choice == "📈 Wealth":
            import pages.wealth as w
            w.render_page(supabase)
        elif choice == "🧾 Tax Planner":
            tax_planner.render_page(supabase)
        elif choice == "🎯 Goals & Protection":
            import pages.goals as g
            g.render_page(supabase)
        elif choice == "👨‍👩‍👧 Family & Legacy":
            import pages.family_legacy as fl
            fl.render_page(supabase)
        elif choice == "🤖 AI CA Advisor":
            ai_advisor.render_page(supabase)


elif st.session_state.show_auth_page:
    # Adopt browser-filled credentials into Streamlit state FIRST so the
    # widgets render with any password-manager values (see auth_autofill_reader).
    _autofill_echo(st.session_state.auth_mode)

    st.markdown("""
    <style>
        [data-testid="stHeader"] { visibility: hidden; }
        
        [data-testid="stVerticalBlockBlockWrapper"] {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid rgba(150, 150, 150, 0.2) !important;
            border-radius: 20px !important;
            padding: 2rem 2.5rem !important;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.05) !important;
            margin-top: 1rem;
        }
        div[data-testid="stTextInput"] label { display: none; }
        div[data-testid="stTextInput"] input {
            background-color: var(--background-color) !important; 
            border: 1px solid rgba(150, 150, 150, 0.2) !important;
            color: var(--text-color) !important; 
            border-radius: 12px !important;
            padding: 0.75rem 1rem !important;
        }
        
        /* Primary button — always a vivid gradient so it's visible in both themes */
        div[data-testid="stButton"] button[kind="primary"] {
            border-radius: 12px !important;
            font-weight: 800 !important;
            font-size: 1.1rem !important;
            border: none !important;
            padding: 0.75rem !important;
            transition: all 0.3s ease;
            background: linear-gradient(135deg, #2563EB, #9333EA) !important;
            color: #FFFFFF !important;
            box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3) !important;
        }
        div[data-testid="stButton"] button[kind="primary"] p {
            color: #FFFFFF !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(37, 99, 235, 0.4) !important;
            filter: brightness(1.1);
        }
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: transparent !important;
            color: var(--text-color) !important;
            opacity: 0.8 !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover { opacity: 1 !important; }
        .forgot-pwd-btn button p { font-weight: 800 !important; }
    </style>
    """, unsafe_allow_html=True)

    st.button("← Back to Home", on_click=go_back_home)
    st.write("")

    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        with st.container(border=True):
            if st.session_state.auth_mode == 'login':
                st.markdown("<h1 style='text-align: center; color: var(--text-color); margin-bottom: 0.2rem; margin-top: 0; font-size: 2.2rem; font-weight: 800;'>Welcome Back</h1>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; font-size: 1.1rem;'>Please log in to your account</p>", unsafe_allow_html=True)
                login_email = st.text_input("Email", placeholder="👤   Email Address", key="login_email")
                login_password = st.text_input("Password", placeholder="🔒   Password", type="password", key="login_password")
                cc1, cc_space, cc2 = st.columns([1.5, 0.5, 1.5])
                with cc1:
                    st.checkbox("Remember me")
                with cc2:
                    st.markdown('<div class="forgot-pwd-btn">', unsafe_allow_html=True)
                    st.button("**Forgot Password?**", on_click=lambda: st.session_state.update(auth_mode='reset'), use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                st.write("") 
                if st.button("Log In", use_container_width=True, type="primary"):
                    try:
                        response = supabase.auth.sign_in_with_password({"email": login_email, "password": login_password})
                        st.session_state.logged_in = True
                        st.session_state.user_email = response.user.email
                        st.session_state.user_id = response.user.id
                        st.session_state.show_auth_page = False
                        # Remember the tokens so the session_keep component can
                        # persist them across a refresh (see the restore block).
                        _sess = getattr(response, "session", None)
                        st.session_state["_auth_access"] = getattr(_sess, "access_token", "") if _sess else ""
                        st.session_state["_auth_refresh"] = getattr(_sess, "refresh_token", "") if _sess else ""
                        st.rerun()
                    except Exception as e:
                        st.error("Login failed. Please check your email and password.")
                st.write("---")
                st.button("Don't have an account? **Sign Up**", use_container_width=True, on_click=lambda: st.session_state.update(auth_mode='signup'))

            elif st.session_state.auth_mode == 'signup':
                st.markdown("<h1 style='text-align: center; color: var(--text-color); margin-bottom: 0.2rem; margin-top: 0; font-size: 2.2rem; font-weight: 800;'>Create Account</h1>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; font-size: 1.1rem;'>Join FinGuru today</p>", unsafe_allow_html=True)
                signup_email = st.text_input("Email", placeholder="👤   Email Address", key="signup_email")
                signup_password = st.text_input("Password", placeholder="🔒   Password (min 6 chars)", type="password", key="signup_password")
                st.write("")
                if st.button("Sign Up", use_container_width=True, type="primary"):
                    try:
                        response = supabase.auth.sign_up({"email": signup_email, "password": signup_password})
                        st.success("Account created successfully! You can now log in.")
                        st.session_state.auth_mode = 'login'
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sign up failed: {e}")
                st.write("---")
                st.button("Already have an account? **Log In**", use_container_width=True, on_click=lambda: st.session_state.update(auth_mode='login'))

            elif st.session_state.auth_mode == 'reset':
                st.markdown("<h1 style='text-align: center; color: var(--text-color); margin-bottom: 0.2rem; margin-top: 0; font-size: 2.2rem; font-weight: 800;'>Reset Password</h1>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; font-size: 1.1rem;'>Enter your email to receive a secure link.</p>", unsafe_allow_html=True)
                reset_email = st.text_input("Email", placeholder="👤   Email Address", key="reset_email_input")
                st.write("")
                if st.button("Send Reset Link", use_container_width=True, type="primary"):
                    if not reset_email:
                        st.warning("Please enter your email address first.")
                    else:
                        try:
                            # Point the emailed link back at the app the user is
                            # actually viewing (localhost in dev, the deployed
                            # host in prod) so it opens the New-Password form.
                            # Falls back to Supabase's default Site URL if this
                            # host isn't whitelisted in Auth → Redirect URLs.
                            redirect_to = _app_base_url()
                            try:
                                supabase.auth.reset_password_for_email(
                                    reset_email,
                                    {"redirect_to": redirect_to} if redirect_to else None,
                                )
                            except Exception:
                                supabase.auth.reset_password_for_email(reset_email)
                            st.success("✅ Secure link sent! Please check your inbox.")
                        except Exception as e:
                            st.error(f"Failed to send link: {e}")
                st.write("---")
                st.button("← Back to Log In", use_container_width=True, on_click=lambda: st.session_state.update(auth_mode='login'))

            elif st.session_state.auth_mode == 'update_pwd':
                st.markdown("<h1 style='text-align: center; color: var(--text-color); margin-bottom: 0.2rem; margin-top: 0; font-size: 2.2rem; font-weight: 800;'>New Password</h1>", unsafe_allow_html=True)
                st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.7; margin-bottom: 2rem; font-size: 1.1rem;'>Enter your new secure password below.</p>", unsafe_allow_html=True)
                new_password = st.text_input("New Password", placeholder="🔒   New Password", type="password", key="new_pwd_input")
                st.write("")
                if st.button("Save New Password", use_container_width=True, type="primary"):
                    if not new_password:
                        st.warning("Please enter a new password.")
                    elif len(new_password) < 6:
                        st.warning("Password must be at least 6 characters.")
                    else:
                        try:
                            supabase.auth.update_user({"password": new_password})
                            # Drop the one-time recovery session so the next login
                            # uses the freshly reset password.
                            supabase.auth.sign_out()
                            # Also drop any browser-persisted session — if one
                            # existed it belongs to the previous password.
                            st.session_state._persist_clear = True
                            st.session_state["_auth_access"] = ""
                            st.session_state["_auth_refresh"] = ""
                            st.success("✅ Password updated! Please log in with your new password.")
                            st.query_params.clear()
                            st.session_state.auth_mode = 'login'
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update password. Did you click the link in your email? Error: {e}")
                st.write("---")
                st.button("← Back to Log In", use_container_width=True, on_click=lambda: st.session_state.update(auth_mode='login'))

        # Enable browser password-manager autofill on whichever auth form is
        # showing (login/signup/reset/update_pwd).
        components.html(
            _AUTH_AUTOFILL_SCRIPT.replace("__AUTH_MODE__", st.session_state.auth_mode),
            height=0,
        )

else:
    # ==========================================
    # ✨ PRODUCTION LANDING PAGE (pre-login)
    # ==========================================
    st.markdown("""
    <div class="landing-hero">
        <div class="landing-eyebrow">AI-Powered Financial Management</div>
        <h1>Manage your money with precision</h1>
        <p class="landing-sub">
            Track spending, compute your taxes, plan retirement, and protect your wealth —
            all grounded in your real numbers. No estimates, no invented data.
        </p>
        <div class="hero-pills">
            <span class="hero-pill">Tax computed on audited rules</span>
            <span class="hero-pill">Monte Carlo retirement planning</span>
            <span class="hero-pill">AI that answers from your data</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1.5, 1, 1.5])
    with c2:
        st.button("Create Free Account", on_click=go_to_auth, use_container_width=True, type="primary")

    st.write("")
    st.markdown("""
    <div class="trust-badges">
        <span class="trust-badge">🔒 AES-256 Encryption</span>
        <span class="trust-badge">🏛️ RBI Account Aggregator</span>
        <span class="trust-badge">📜 DPDP Act 2023 Compliant</span>
    </div>
    """, unsafe_allow_html=True)

    st.write("---")

    # ====== What FinGuru covers — the 7 areas ======
    st.markdown("""
    <div class="section-head">
        <div class="section-eyebrow">Capabilities</div>
        <h2>One platform for your entire financial life</h2>
        <p>Seven focused areas, computed from your real data with deterministic engines and a grounded AI advisor.</p>
    </div>
    """, unsafe_allow_html=True)

    capabilities = [
        ("📊", "Transactions & Budgeting", "Track every rupee, auto-catch anomalous and hidden spending, and know exactly how much is safe to spend.", ["Spend", "Alerts", "Budgets"]),
        ("📈", "Wealth", "Your portfolio, net worth and borrowing power — tracked and computed, not guessed.", ["Portfolio", "Net Worth", "Loans"]),
        ("🧾", "Tax Planning", "Old vs New regime compared side by side with your actual deductions, so you keep more of your income.", ["Old vs New", "Deductions", "Savings"]),
        ("🎯", "Goals & Protection", "Retirement probability via Monte Carlo, tailored insurance cover, and safety guardrails.", ["Retirement", "Insurance", "Protection"]),
        ("👨‍👩‍👧", "Family & Legacy", "A consolidated view across family, with asset-to-successor mapping for the next generation.", ["Family", "Legacy", "Inheritance"]),
        ("🤖", "AI CA Advisor", "A grounded advisor that answers from your computed figures — never from invented data.", ["Chat", "Grounded", "Anytime"]),
    ]
    render_module_grid(capabilities)

    st.write("---")

    # ====== How It Works ======
    st.markdown("""
    <div class="section-head">
        <div class="section-eyebrow">Getting Started</div>
        <h2>Three steps to full visibility</h2>
    </div>
    """, unsafe_allow_html=True)
    hw1, hw2, hw3 = st.columns(3)
    with hw1:
        st.markdown("""<div class="step"><div class="step-num">1</div><h4>Create Account</h4><p>Sign up securely in seconds. Nothing to install.</p></div>""", unsafe_allow_html=True)
    with hw2:
        st.markdown("""<div class="step"><div class="step-num">2</div><h4>Add Your Money</h4><p>Link banks via RBI Account Aggregator or log transactions manually.</p></div>""", unsafe_allow_html=True)
    with hw3:
        st.markdown("""<div class="step"><div class="step-num">3</div><h4>Optimize & Plan</h4><p>Compare tax regimes, simulate retirement, and chat with your AI advisor.</p></div>""", unsafe_allow_html=True)

    st.write("---")

    # ====== Privacy & Security ======
    with st.container(border=True):
        st.markdown("<h3 style='text-align: center; font-size: 1.05rem; font-weight: 600;'>🛡️ Privacy & Security</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; opacity: 0.6; font-size: 0.85rem;'>Your financial data is yours. FinGuru operates under the DPDP Act 2023 with enterprise-grade protections.</p>", unsafe_allow_html=True)
        p1, p2 = st.columns(2)
        p1.markdown("✔️ **Encryption at rest & transit:** AES-256 symmetric encryption for sensitive fields; TLS 1.3 for all network traffic.")
        p2.markdown("✔️ **Row-level security:** Every query is scoped to your account — cross-user data access is impossible even with DB access.")
        st.write("")
        p3, p4 = st.columns(2)
        p3.markdown("✔️ **Anonymized AI:** Your name, email and account numbers are never sent to the AI. Only computed amounts and categories.")
        p4.markdown("✔️ **Right to be forgotten:** Delete all your data with one click — records, transactions and profiles are permanently removed.")

    st.write("---")

    st.markdown("<h2 style='text-align: center; font-size: 1.3rem; font-weight: 700;'>Ready to take control?</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.6; margin-bottom: 1.5rem; font-size: 0.9rem;'>Every number is computed. Every insight is grounded in your data.</p>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns([1.5, 1, 1.5])
    with fc2:
        st.button("Create Free Account", type="primary", use_container_width=True, on_click=go_to_auth, key="footer_btn")
    st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.5; font-size: 0.78rem; margin-top: 2.5rem;'>© 2026 FinGuru. All rights reserved.</p>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: var(--text-color); opacity: 0.35; font-size: 0.68rem;'>FinGuru is an educational financial planning tool. Always consult a certified financial advisor before making investment or tax decisions.</p>", unsafe_allow_html=True)


# ==========================================
# ✨ PERSIST SESSION — WRITE-BACK (runs after routing)
# Stores the page the user is actually on. On a fresh visit the correction above
# already forced the landing page, so this re-persists the landing page over the
# stale "last module" in the same run — a full reopen starts clean next time.
# A same-tab refresh keeps its module because "reload" never triggered the
# correction. The component is change-gated: an identical store writes nothing.
# ==========================================
if not (_recovery_folded or _recovery_consumed):
    try:
        if st.session_state.logged_in and not _persist_clear_requested:
            _session_keep(store=_persist_json() or "")
        elif _persist_clear_requested:
            _session_keep(clear=True)
    except Exception:
        pass
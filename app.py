"""
currencyConverter - Streamlit app
Run:  streamlit run currency_converter.py
Deps: pip install streamlit requests pandas plotly

Changes vs. the original
- Flags are real images (flagcdn.com), so they render on Windows (which has no flag emoji).
- Country selection is a true drum / wheel picker (custom Streamlit component, written to
  disk automatically on first run, so this is still a single file).
- Plain (unruled) paper-notebook theme.
- Live conversion (no button needed), swap button, cached API calls, timeouts, error handling.
- History tab: more ranges, stats (latest / change / high / low), average line.
- Removed the fragile Lottie dependency and the brittle CSS selectors.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import streamlit.components.v1 as components

API = "https://api.frankfurter.dev/v1"
TIMEOUT = 10

st.set_page_config(page_title="currencyConverter", page_icon="💱", layout="centered")

# --------------------------------------------------------------------------------------
# CURRENCY METADATA  (code -> ISO-2 country code for flag image, display name, symbol)
# --------------------------------------------------------------------------------------
CURRENCY_DATA = {
    "AUD": ("au", "Australia", "A$"),
    "BGN": ("bg", "Bulgaria", "лв"),
    "BRL": ("br", "Brazil", "R$"),
    "CAD": ("ca", "Canada", "C$"),
    "CHF": ("ch", "Switzerland", "CHF"),
    "CNY": ("cn", "China", "¥"),
    "CZK": ("cz", "Czechia", "Kč"),
    "DKK": ("dk", "Denmark", "kr"),
    "EUR": ("eu", "Euro Area", "€"),
    "GBP": ("gb", "United Kingdom", "£"),
    "HKD": ("hk", "Hong Kong", "HK$"),
    "HUF": ("hu", "Hungary", "Ft"),
    "IDR": ("id", "Indonesia", "Rp"),
    "ILS": ("il", "Israel", "₪"),
    "INR": ("in", "India", "₹"),
    "ISK": ("is", "Iceland", "kr"),
    "JPY": ("jp", "Japan", "¥"),
    "KRW": ("kr", "South Korea", "₩"),
    "MXN": ("mx", "Mexico", "Mex$"),
    "MYR": ("my", "Malaysia", "RM"),
    "NOK": ("no", "Norway", "kr"),
    "NZD": ("nz", "New Zealand", "NZ$"),
    "PHP": ("ph", "Philippines", "₱"),
    "PLN": ("pl", "Poland", "zł"),
    "RON": ("ro", "Romania", "lei"),
    "SEK": ("se", "Sweden", "kr"),
    "SGD": ("sg", "Singapore", "S$"),
    "THB": ("th", "Thailand", "฿"),
    "TRY": ("tr", "Türkiye", "₺"),
    "USD": ("us", "United States", "$"),
    "ZAR": ("za", "South Africa", "R"),
}


def flag_html(code: str, height: int = 22) -> str:
    iso = CURRENCY_DATA.get(code, ("", "", ""))[0]
    if not iso:
        return ""
    return (
        f'<img class="flag" height="{height}" alt="{code}" '
        f'src="https://flagcdn.com/w40/{iso}.png" '
        f'srcset="https://flagcdn.com/w80/{iso}.png 2x">'
    )


def symbol(code: str) -> str:
    return CURRENCY_DATA.get(code, ("", "", code))[2]


def fmt(x: float) -> str:
    return f"{x:,.2f}" if abs(x) >= 0.01 else f"{x:,.6f}"


# --------------------------------------------------------------------------------------
# API LAYER (cached, with timeouts)
# --------------------------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def get_currencies() -> dict:
    try:
        r = requests.get(f"{API}/currencies", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_rate(base: str, target: str) -> tuple[float, str]:
    r = requests.get(f"{API}/latest", params={"base": base, "symbols": target}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return float(data["rates"][target]), data.get("date", "")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(base: str, target: str, start: str, end: str) -> dict:
    r = requests.get(
        f"{API}/{start}..{end}",
        params={"base": base, "symbols": target},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    rates = r.json().get("rates", {})
    return {d: v[target] for d, v in rates.items() if target in v}


# --------------------------------------------------------------------------------------
# DRUM / WHEEL PICKER  (bidirectional custom component, no build step needed)
# --------------------------------------------------------------------------------------
WHEEL_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  :root { --ink:#1f2a44; --accent:#2b59c3; --paper:#fffdf7; }
  * { box-sizing:border-box; }
  html,body { margin:0; background:transparent; font-family:'Courier New',Courier,monospace; color:var(--ink); }
  #q { width:100%; height:32px; margin-bottom:8px; padding:0 12px; border:1.5px solid #cfc6b0;
       border-radius:16px; background:#fff; font:inherit; font-size:13px; color:var(--ink); outline:none; }
  #q:focus { border-color:var(--accent); }
  .drum { position:relative; height:200px; border:2px solid #cfc6b0; border-radius:22px; overflow:hidden;
          background:linear-gradient(180deg,#efe8d6 0%,#fffdf7 28%,#fffdf7 72%,#efe8d6 100%);
          box-shadow:inset 0 8px 14px rgba(80,60,20,.12), inset 0 -8px 14px rgba(80,60,20,.12); }
  .band { position:absolute; left:8px; right:8px; top:77px; height:46px; border-radius:14px; pointer-events:none;
          border:2px solid var(--accent); background:rgba(43,89,195,.07); z-index:2; }
  #wheel { height:100%; overflow-y:scroll; scroll-snap-type:y mandatory; perspective:700px;
           scrollbar-width:none; outline:none; cursor:grab; -webkit-mask-image:linear-gradient(transparent 0,#000 22%,#000 78%,transparent 100%);
           mask-image:linear-gradient(transparent 0,#000 22%,#000 78%,transparent 100%); }
  #wheel::-webkit-scrollbar { display:none; }
  .spacer { height:77px; }
  .item { height:46px; display:flex; align-items:center; gap:12px; padding:0 22px; scroll-snap-align:center;
          transform-origin:center; will-change:transform; user-select:none; }
  .item .fl { width:32px; height:22px; flex:none; display:flex; align-items:center; justify-content:center; }
  .item img { width:32px; height:22px; object-fit:cover; border-radius:3px; box-shadow:0 0 0 1px rgba(0,0,0,.18); }
  .item .nm { flex:1; font-size:15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item .cd { font-weight:bold; font-size:15px; }
  .item .sy { width:38px; text-align:right; color:#6b7280; font-size:14px; }
  .item.active .nm, .item.active .cd { color:var(--accent); }
</style></head>
<body>
  <input id="q" type="text" placeholder="type a country or code to jump...">
  <div class="drum">
    <div class="band"></div>
    <div id="wheel" tabindex="0"><div class="spacer"></div><div id="list"></div><div class="spacer"></div></div>
  </div>
<script>
  const ITEM = 46;
  const wheel = document.getElementById('wheel');
  const list = document.getElementById('list');
  const q = document.getElementById('q');
  let opts = [], optsKey = '', items = [], sent = null, lastSelected = null, timer = null;
  const recent = {};   /* values this wheel sent recently: their echo from Python must not move the wheel */
  let drag = null, suppress = false;

  function post(type, data) {
    window.parent.postMessage(Object.assign({isStreamlitMessage: true, type: type}, data || {}), '*');
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }
  function build() {
    list.innerHTML = '';
    items = opts.map((o, i) => {
      const d = document.createElement('div');
      d.className = 'item';
      const flag = o.iso
        ? '<img src="https://flagcdn.com/w80/' + o.iso + '.png" alt="" onerror="this.style.display=\'none\'">'
        : '';
      d.innerHTML = '<span class="fl">' + flag + '</span><span class="nm">' + esc(o.name) +
                    '</span><span class="cd">' + o.code + '</span><span class="sy">' + esc(o.symbol) + '</span>';
      d.addEventListener('click', () => goTo(i, true));
      list.appendChild(d);
      return d;
    });
  }
  function idx() {
    return Math.max(0, Math.min(opts.length - 1, Math.round(wheel.scrollTop / ITEM)));
  }
  let anim = null, animTarget = null, lastStep = 0;
  function goTo(i, smooth) {
    i = Math.max(0, Math.min(opts.length - 1, i));
    cancelAnimationFrame(anim);
    const target = i * ITEM, start = wheel.scrollTop;
    if (!smooth) { animTarget = null; wheel.scrollTop = target; return; }
    if (Math.abs(target - start) < 1) { animTarget = null; return; }
    animTarget = i;
    const dur = Math.min(320, 110 + Math.abs(target - start) / ITEM * 12);
    const t0 = performance.now();
    wheel.style.scrollSnapType = 'none';
    const step = now => {
      const p = Math.min(1, (now - t0) / dur);
      wheel.scrollTop = start + (target - start) * (1 - Math.pow(1 - p, 3));
      if (p < 1) { anim = requestAnimationFrame(step); }
      else { animTarget = null; wheel.style.scrollSnapType = ''; }
    };
    anim = requestAnimationFrame(step);
  }
  /* mouse wheel / trackpad: exactly one item per step, no runaway momentum */
  wheel.addEventListener('wheel', e => {
    e.preventDefault();
    const now = performance.now();
    if (Math.abs(e.deltaY) < 4 || now - lastStep < 120) return;
    lastStep = now;
    const base = animTarget !== null ? animTarget : idx();
    goTo(base + (e.deltaY > 0 ? 1 : -1), true);
  }, {passive: false});
  function drum() {
    const top = wheel.scrollTop;
    items.forEach((el, i) => {
      const d = (i * ITEM - top) / ITEM;
      const a = Math.min(Math.abs(d), 3);
      el.style.transform = 'rotateX(' + Math.max(-70, Math.min(70, -d * 22)) + 'deg) scale(' + (1 - a * 0.07) + ')';
      el.style.opacity = Math.max(0.15, 1 - Math.abs(d) * 0.28);
    });
  }
  function settle() {
    const i = idx();
    items.forEach((el, k) => el.classList.toggle('active', k === i));
    const v = opts[i] && opts[i].code;
    if (v && v !== sent) {
      sent = v;
      recent[v] = performance.now();
      post('streamlit:setComponentValue', {value: v, dataType: 'json'});
    }
  }
  wheel.addEventListener('scroll', () => {
    requestAnimationFrame(drum);
    clearTimeout(timer);
    timer = setTimeout(settle, 90);
  });
  wheel.addEventListener('keydown', e => {
    const base = animTarget !== null ? animTarget : idx();
    if (e.key === 'ArrowDown') { e.preventDefault(); goTo(base + 1, true); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); goTo(base - 1, true); }
  });
  let qTimer = null;
  function jump() {
    const t = q.value.trim().toLowerCase();
    if (!t) return;
    let i = opts.findIndex(o => o.code.toLowerCase() === t);
    if (i < 0) i = opts.findIndex(o => o.name.toLowerCase() === t);
    if (i < 0) i = opts.findIndex(o => o.name.toLowerCase().startsWith(t));
    if (i < 0) i = opts.findIndex(o => (o.name + ' ' + o.code).toLowerCase().includes(t));
    if (i >= 0) goTo(i, true);
  }
  q.addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(jump, 350); });
  q.addEventListener('keydown', e => { if (e.key === 'Enter') { clearTimeout(qTimer); jump(); } });
  /* mouse drag (touch / trackpad scroll natively) */
  wheel.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse') return;
    drag = {y: e.clientY, top: wheel.scrollTop, moved: false};
  });
  window.addEventListener('pointermove', e => {
    if (!drag) return;
    const dy = e.clientY - drag.y;
    if (Math.abs(dy) > 4) {
      drag.moved = true;
      wheel.style.scrollSnapType = 'none';
      wheel.style.cursor = 'grabbing';
      wheel.scrollTop = drag.top - dy;
    }
  });
  window.addEventListener('pointerup', () => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    wheel.style.cursor = '';
    if (moved) {
      suppress = true;
      wheel.style.scrollSnapType = '';
      goTo(idx(), true);
    }
  });
  wheel.addEventListener('click', e => {
    if (suppress) { e.stopPropagation(); e.preventDefault(); suppress = false; }
  }, true);

  function render(args) {
    const key = JSON.stringify(args.options);
    if (key !== optsKey) { optsKey = key; opts = args.options; build(); }
    if (args.selected !== lastSelected) {
      const first = lastSelected === null;
      lastSelected = args.selected;
      const i = Math.max(0, opts.findIndex(o => o.code === args.selected));
      if (first) sent = args.selected;     /* python already holds this value */
      const echo = recent[args.selected] && (performance.now() - recent[args.selected] < 2500);
      if (first || !echo) {                /* only external changes (e.g. swap) move the wheel */
        goTo(i, false);
        drum();
        items.forEach((el, k) => el.classList.toggle('active', k === i));
      }
    }
    post('streamlit:setFrameHeight', {height: 250});
  }
  window.addEventListener('message', e => {
    if (e.data && e.data.type === 'streamlit:render') render(e.data.args);
  });
  post('streamlit:componentReady', {apiVersion: 1});
  post('streamlit:setFrameHeight', {height: 250});
</script>
</body></html>
"""


def _declare_wheel():
    comp_dir = Path(__file__).resolve().parent / ".wheel_component"
    comp_dir.mkdir(exist_ok=True)
    index = comp_dir / "index.html"
    if not index.exists() or index.read_text(encoding="utf-8") != WHEEL_HTML:
        index.write_text(WHEEL_HTML, encoding="utf-8")
    return components.declare_component("currency_wheel", path=str(comp_dir))


_wheel = _declare_wheel()


def wheel_picker(key: str, options: list[dict]) -> str:
    """Render a drum picker. The chosen currency code lives in st.session_state[key]."""
    current = st.session_state[key]
    value = _wheel(options=options, selected=current, key=f"{key}_wheel", default=current)
    seen_key = f"{key}_seen"
    if seen_key not in st.session_state:
        st.session_state[seen_key] = value
    # Only accept the widget's value if the *user* moved the wheel (value changed on the
    # frontend). This keeps programmatic changes (the swap button) from being overwritten.
    if value != st.session_state[seen_key]:
        st.session_state[seen_key] = value
        st.session_state[key] = value
    return st.session_state[key]


# --------------------------------------------------------------------------------------
# THEME: plain (unruled) paper notebook
# --------------------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&display=swap');

.stApp {
    color-scheme: light;
    background-color: #fbf7ec;
    background-attachment: fixed;
    min-height: 100vh;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.45  0 0 0 0 0.38  0 0 0 0 0.25  0 0 0 0.08 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
}
html, body { background: #fbf7ec; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main, .main { background: transparent !important; }
header[data-testid="stHeader"] { background: transparent; }

/* content sits directly on the full-screen paper */
.block-container {
    max-width: 820px;
    padding: 2.5rem 2rem 3rem !important;
    background: transparent;
}

h1, h2, h3, p, label, li, .stMarkdown, [data-testid="stWidgetLabel"] p {
    font-family: 'Courier Prime', 'Courier New', Courier, monospace;
    color: #1f2a44 !important;
}
h1 { letter-spacing: -0.5px; }

/* bordered containers = paper cards */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fffefb;
    border: 1.5px solid #d9cfb6 !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 0 #eee6d2;
}

/* inputs */
div[data-baseweb="input"], div[data-baseweb="base-input"], input {
    background: #ffffff !important;
    color: #1f2a44 !important;
    font-family: 'Courier Prime', 'Courier New', monospace !important;
}
div[data-baseweb="input"] { border-radius: 12px !important; }

/* buttons */
.stButton > button {
    background: #1f2a44;
    color: #fffdf7;
    border: none;
    border-radius: 30px;
    padding: 0.55rem 1.2rem;
    font-weight: 700;
    font-family: 'Courier Prime', 'Courier New', monospace;
    transition: transform .15s, box-shadow .15s, background .15s;
}
.stButton > button:hover {
    background: #2b59c3; color: #fff;
    transform: translateY(-2px); box-shadow: 0 8px 16px rgba(43, 89, 195, .3);
}
.stButton > button:active { transform: translateY(0); }

/* tabs */
button[data-baseweb="tab"] { font-family: 'Courier Prime', 'Courier New', monospace; }

/* flags + result card */
img.flag { border-radius: 3px; box-shadow: 0 0 0 1px rgba(0,0,0,.18); vertical-align: middle; }
.result {
    margin-top: .6rem; padding: 1.3rem 1.5rem; border-radius: 16px;
    background: #f4efe1; border: 1.5px dashed #b9ad8b; font-family: 'Courier Prime', 'Courier New', monospace;
}
.result .from { font-size: 1.05rem; color: #5b6475; }
.result .to { font-size: 2.1rem; font-weight: 700; color: #1f2a44; margin-top: .2rem; word-break: break-word; }
.result .meta { margin-top: .6rem; font-size: .85rem; color: #6b7280; }
.pick-label { font-family: 'Courier Prime', monospace; font-weight: 700; color: #1f2a44; margin: 0 0 .35rem; }
.pick-label span { color: #2b59c3; }
</style>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------------------
# DATA / STATE
# --------------------------------------------------------------------------------------
api_currencies = get_currencies()
if api_currencies:
    codes = sorted(api_currencies)
else:
    codes = sorted(CURRENCY_DATA)
    st.warning("Couldn't reach the exchange-rate service for the currency list; using the built-in list.")

options = []
for c in codes:
    iso, name, sym = CURRENCY_DATA.get(c, ("", api_currencies.get(c, c), c))
    options.append({"code": c, "iso": iso, "name": name, "symbol": sym})
options.sort(key=lambda o: o["name"].lower())

for k, default in (("conv_from", "USD"), ("conv_to", "EUR"), ("hist_base", "USD"), ("hist_target", "EUR")):
    if k not in st.session_state or st.session_state[k] not in codes:
        st.session_state[k] = default if default in codes else codes[0]


def swap(a: str, b: str):
    st.session_state[a], st.session_state[b] = st.session_state[b], st.session_state[a]


def picker_pair(key_a: str, key_b: str, label_a: str, label_b: str):
    c1, cm, c2 = st.columns([10, 2, 10], vertical_alignment="center")
    with c1:
        st.markdown(
            f'<p class="pick-label">{label_a} <span>{st.session_state[key_a]}</span></p>',
            unsafe_allow_html=True,
        )
        a = wheel_picker(key_a, options)
    with cm:
        st.button("⇄", key=f"swap_{key_a}", on_click=swap, args=(key_a, key_b), help="Swap currencies")
    with c2:
        st.markdown(
            f'<p class="pick-label">{label_b} <span>{st.session_state[key_b]}</span></p>',
            unsafe_allow_html=True,
        )
        b = wheel_picker(key_b, options)
    return a, b


def show_chart(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:  # older Streamlit
        st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------------------
st.title("🌐 currencyConverter")
st.markdown("**Live global exchange rates & history**")

tab1, tab2 = st.tabs(["💱 Convert", "📈 Compare & History"])

# ---------------- TAB 1: CONVERT ----------------
with tab1:
    with st.container(border=True):
        amount = st.number_input("Amount to convert", min_value=0.01, value=1.00, step=1.00, format="%.2f")
        from_curr, to_curr = picker_pair("conv_from", "conv_to", "From:", "To:")

    if from_curr == to_curr:
        st.info("Pick two different currencies to see a conversion.")
    else:
        try:
            with st.spinner("Fetching latest rate..."):
                rate, rate_date = fetch_rate(from_curr, to_curr)
            result = amount * rate
            st.markdown(
                f"""<div class="result">
<div class="from">{flag_html(from_curr)} {symbol(from_curr)}{fmt(amount)} {from_curr} =</div>
<div class="to">{flag_html(to_curr, 30)} {symbol(to_curr)}{fmt(result)} <small>{to_curr}</small></div>
<div class="meta">1 {from_curr} = {rate:,.6g} {to_curr} &nbsp;·&nbsp; 1 {to_curr} = {1 / rate:,.6g} {from_curr}
&nbsp;·&nbsp; rates as of {rate_date} (ECB reference rates)</div>
</div>""",
                unsafe_allow_html=True,
            )
        except (requests.RequestException, KeyError, ValueError, ZeroDivisionError):
            st.error("Couldn't fetch the exchange rate right now. Please try again in a moment.")

# ---------------- TAB 2: HISTORY ----------------
with tab2:
    st.subheader("Historical comparison")
    with st.container(border=True):
        hist_base, hist_target = picker_pair("hist_base", "hist_target", "Base:", "Target:")
        ranges = {"1 Month": 30, "3 Months": 90, "6 Months": 182, "1 Year": 365, "5 Years": 1825}
        timeframe = st.radio("Timeframe", list(ranges), index=1, horizontal=True)

    if hist_base == hist_target:
        st.info("Pick two different currencies to see a chart.")
    else:
        end = date.today()
        start = end - timedelta(days=ranges[timeframe])
        try:
            with st.spinner("Loading historical data..."):
                series = fetch_history(hist_base, hist_target, start.isoformat(), end.isoformat())
            if not series:
                st.error("Historical data isn't available for this pair.")
            else:
                df = pd.DataFrame({"Date": pd.to_datetime(list(series)), "Rate": list(series.values())})
                df = df.sort_values("Date").reset_index(drop=True)

                latest, first = df["Rate"].iloc[-1], df["Rate"].iloc[0]
                change = (latest / first - 1) * 100
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Latest", f"{latest:,.4f}")
                m2.metric(f"Change ({timeframe})", f"{change:+.2f}%", f"{change:+.2f}%", label_visibility="visible")
                m3.metric("High", f"{df['Rate'].max():,.4f}")
                m4.metric("Low", f"{df['Rate'].min():,.4f}")

                fig = px.line(df, x="Date", y="Rate", title=f"{hist_base} → {hist_target}  ({timeframe})")
                fig.update_traces(line_color="#2b59c3", line_width=2.5,
                                  hovertemplate="%{x|%d %b %Y}<br>%{y:.4f}<extra></extra>")
                fig.add_hline(y=df["Rate"].mean(), line_dash="dot", line_color="#b9ad8b",
                              annotation_text="average", annotation_position="top left")
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#1f2a44", family="Courier New"),
                    xaxis=dict(showgrid=False, title=None),
                    yaxis=dict(showgrid=True, gridcolor="rgba(185,173,139,0.35)", title=f"1 {hist_base} in {hist_target}"),
                    margin=dict(l=10, r=10, t=50, b=10),
                )
                show_chart(fig)
        except (requests.RequestException, KeyError, ValueError):
            st.error("Unable to load historical data right now. Please try again shortly.")

st.caption("Rates: Frankfurter API (European Central Bank reference rates, updated on working days). Flags: flagcdn.com.")
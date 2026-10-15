import { Component, useEffect, useState } from "react";

export const nf = (n, d = 0) => (n == null || Number.isNaN(Number(n)) ? "–" : Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const pct = (x) => `${Math.round(x * 100)}%`;
export const f2 = (x) => Number(x).toFixed(2);

export const LEVEL = {
  cut_off: ["CRITICAL", "crit"], longer_route: ["WATCH", "watch"], connected: ["NORMAL", "ok"],
  not_assessable: ["NO DATA", "na"], no_road_data: ["NO DATA", "na"],
};
export const LABEL = {
  cut_off: "Cut off", longer_route: "Longer route", connected: "Connected", not_assessable: "Not assessable", no_road_data: "No road data",
};
export const ORDER = ["cut_off", "longer_route", "connected", "not_assessable", "no_road_data"];
const titleCase = (s) => s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
export const pillText = (k) => `${titleCase(LEVEL[k][0])} · ${LABEL[k]}`;

export const Icon = ({ name }) => <span className="msr" aria-hidden="true">{name}</span>;

/* the logo mark and the empty-state illustration (same artwork as the original dashboard) */
const LOGO_SVG =
  "<svg width='44' height='44' viewBox='0 0 48 48' role='img' aria-label='BeaconSpace logo'>" +
  "<path d='M13.0 24.0A11.0 11.0 0 0 1 24.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='1.0'/>" +
  "<path d='M13.0 16.0A19.0 19.0 0 0 1 32.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.62'/>" +
  "<path d='M13.0 8.0A27.0 27.0 0 0 1 40.0 35.0' fill='none' stroke='var(--bs-accent)' stroke-width='3.2' stroke-linecap='round' opacity='0.34'/>" +
  "<circle cx='13.0' cy='35.0' r='5.6' fill='var(--bs-accent)'/><circle cx='32.1' cy='15.9' r='3.3' fill='var(--bs-text)'/></svg>";
const HERO_SVG =
  "<svg viewBox='0 0 220 120' width='220' height='120' role='img' aria-label='Satellite scanning a mountain valley'>" +
  "<path d='M0 100 L50 60 L80 82 L120 40 L170 84 L220 58 L220 120 L0 120Z' fill='var(--bs-surface2)'/>" +
  "<path d='M96 120 C104 96 112 88 110 70 C108 56 116 50 120 40' stroke='var(--bs-accent)' stroke-width='3' fill='none' stroke-linecap='round'/>" +
  "<g transform='translate(150 16)'><rect x='-10' y='-5' width='20' height='10' rx='2' fill='var(--bs-text)' opacity='.85'/>" +
  "<rect x='-27' y='-3' width='13' height='6' fill='var(--bs-muted)'/><rect x='14' y='-3' width='13' height='6' fill='var(--bs-muted)'/></g>" +
  "<path d='M150 24 L112 62 M150 24 L130 62' stroke='var(--bs-accent)' stroke-width='1.6' stroke-dasharray='4 4' opacity='.85'/></svg>";
export const Logo = () => <span style={{ display: "inline-flex" }} dangerouslySetInnerHTML={{ __html: LOGO_SVG }} />;

export function Card({ label, value, sub, delay = 1, dot, unit }) {
  return (
    <div className={`bs-card bs-enter bs-d${delay}`}>
      <div className="bs-label">{dot && <span className="bs-dot" style={{ background: dot }} />}{label}</div>
      <div className="bs-value">{value}{unit && <small>{unit}</small>}</div>
      <div className="bs-sub">{sub}</div>
    </div>
  );
}

export function Badge({ status }) {
  const [text, cls] = LEVEL[status] || ["NO DATA", "na"];
  return <span className={`bs-badge ${cls}`}>{text}</span>;
}

/* body may hold simple inline markup written by us (<b>, <code>); never user data */
export function Empty({ title, body, children, art = true }) {
  return (
    <div className="bs-empty bs-enter">
      {art && <span dangerouslySetInnerHTML={{ __html: HERO_SVG }} />}
      <h3 className="bs-head">{title}</h3>
      <p dangerouslySetInnerHTML={{ __html: body }} />
      {children}
    </div>
  );
}

export const PageTitle = ({ title, sub, style }) => (
  <div className="bs-page" style={style}>
    <h2 className="bs-head">{title}</h2>
    <p>{sub}</p>
  </div>
);

export function Field({ label, help, children, htmlFor }) {
  return (
    <div className="field">
      {label && <label htmlFor={htmlFor}>{label}</label>}
      {children}
      {help && <div className="help">{help}</div>}
    </div>
  );
}

export function Check({ checked, onChange, children }) {
  return (
    <label className="chk">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

export function Expander({ title, open: o = false, children }) {
  const [open, setOpen] = useState(o);
  useEffect(() => setOpen(o), [o]);
  return (
    <details className="exp" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>{title}<Icon name="expand_more" /></summary>
      <div className="body">{children}</div>
    </details>
  );
}

export function Skeleton() {
  return (
    <div className="bs-card" role="status" aria-live="polite" aria-label="Loading results">
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <div className="bs-spin" />
        <div className="bs-head" style={{ fontSize: 22 }}>Loading results…</div>
      </div>
      <div className="bs-grid" style={{ margin: "16px 0 0" }}>
        {[0, 1, 2, 3].map((i) => <div key={i} className="bs-skel" style={{ height: 120 }} />)}
      </div>
    </div>
  );
}

export function Progress({ step, steps, lines, title = "Analysing…", elapsed }) {
  return (
    <div className="bs-card bs-enter" role="status" aria-live="polite">
      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <div className="bs-spin" />
        <div>
          <div className="bs-head" style={{ fontSize: 22 }}>{title}{elapsed ? <span className="bs-mono" style={{ fontSize: 14, fontWeight: 500, color: "var(--bs-muted)", marginLeft: 12 }}>{elapsed} s</span> : null}</div>
          <div className="bs-sub">Streaming Sentinel data and building the road graph. First runs of a new area take a few minutes.</div>
        </div>
      </div>
      <div className="bs-stepper">
        {steps.map((n, i) => <div key={n} className={`bs-step ${i < step ? "done" : i === step ? "now" : ""}`}>{n}</div>)}
      </div>
      <div className="bs-grid" style={{ margin: "0 0 16px" }}>
        {[0, 1, 2, 3].map((i) => <div key={i} className="bs-skel" style={{ height: 120 }} />)}
      </div>
      <div className="bs-log">{lines.join("\n")}</div>
    </div>
  );
}

export class ErrorBoundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <Empty title="Something went wrong on this page" body="The page hit an unexpected error. Reload it, or pick another page from the navigation bar.">
        <button className="btn" style={{ maxWidth: 240 }} onClick={() => window.location.reload()}>Reload</button>
      </Empty>
    );
  }
}

export const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = j.detail || msg; } catch { /* keep status text */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
};

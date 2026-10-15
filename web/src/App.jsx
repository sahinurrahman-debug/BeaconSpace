import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Empty, ErrorBoundary, Icon, Logo, Skeleton, api } from "./ui.jsx";
import { Ctx, useApp } from "./ctx.js";
import Overview from "./pages/Overview.jsx";
import Settlements from "./pages/Settlements.jsx";
import Report from "./pages/Report.jsx";
import Method from "./pages/Method.jsx";
import Ems from "./pages/Ems.jsx";
import NewAnalysis from "./pages/NewAnalysis.jsx";

const PAGES = [
  ["/overview", "Overview", "dashboard", Overview],
  ["/settlements", "Settlements", "alt_route", Settlements],
  ["/report", "Situation report", "description", Report],
  ["/method", "Method & data", "science", Method],
  ["/ems", "EMS check", "fact_check", Ems],
  ["/new", "New analysis", "play_circle", NewAnalysis],
];

const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const systemLight = () => window.matchMedia("(prefers-color-scheme: light)").matches;

function useTheme() {
  const [pref, setPref] = useState(store.get("bs-theme") || "system");     // system | light | dark
  const [sys, setSys] = useState(systemLight());
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const on = () => setSys(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const theme = pref === "system" ? (sys ? "light" : "dark") : pref;
  useEffect(() => { document.documentElement.setAttribute("data-theme", theme); }, [theme]);
  const cycle = () => { const n = { system: "light", light: "dark", dark: "system" }[pref]; setPref(n); store.set("bs-theme", n); };
  return { pref, theme, cycle };
}

function Nav({ th }) {
  const icon = { system: "contrast", light: "light_mode", dark: "dark_mode" }[th.pref];
  return (
    <header className="bs-nav">
      <nav aria-label="Main">
        {PAGES.map(([to, title, ic]) => (
          <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "active" : "")}>
            <Icon name={ic} /><span className="t">{title}</span>
          </NavLink>
        ))}
      </nav>
      <button className="bs-theme" onClick={th.cycle} title={`Theme: ${th.pref} (click to change)`} aria-label={`Theme: ${th.pref}. Click to change.`}>
        <Icon name={icon} />
      </button>
    </header>
  );
}

function NotFound() {
  return <Empty title="Page not found" body="That address does not exist. Use the navigation bar above to open Overview, Settlements, the report or a new analysis." />;
}

/* Early-monsoon pairs can show false change because the pre-event series ends before the monsoon (null-event test, docs/results). */
function seasonWarning(S) {
  const ev = new Date(S.event_utc);
  if (!(ev.getUTCMonth() >= 5 && ev.getUTCMonth() <= 8)) return null;
  const early = S.s1_pairs.some((p) => new Date(p.pre[0]).getUTCMonth() <= 4 || (new Date(p.pre[0]).getUTCMonth() === 5 && new Date(p.pre[0]).getUTCDate() < 15));
  return early ? "The pre-event radar series for at least one track ends before the monsoon began. Wide, thin 'debris' near rivers can be seasonal change, so treat marginal areas with care." : null;
}

function Strip({ S }) {
  const model = S.model ? S.model.file : "physics only";
  const prov = [...new Set(Object.values(S.osm.provider))].sort().join(", ");
  const passes = S.s1_pairs.map((p) => `RO${p.rel_orbit} ${p.pre[0].slice(5, 10)}→${p.post.slice(5, 10)}`).join(" · ");
  const items = [
    ["FLOOD", `${S.event_utc.slice(0, 16).replace("T", " ")}Z`],
    ["GRID", `${Math.round(S.area_km2).toLocaleString("en-US")} km² · ${Math.round(S.resolution_m)} m`],
    ["S1", passes],
    ["S2", S.s2 ? `${Math.round(S.s2.clear_fraction * 100)}% clear` : "radar only"],
    ["DETECTOR", model],
    ["OSM", `${S.osm.snapshot} · ${prov}`],
    ["RUN", `${Math.round(S.runtime_s)} s`],
  ];
  return <div className="bs-strip">{items.map(([k, v]) => <span key={k}><i>{k}</i>{v}</span>)}</div>;
}

function Shell({ th }) {
  const loc = useLocation();
  const onNew = loc.pathname === "/new";
  const { runs, runsLoaded, sel, setSel, run, runLoading, runError } = useApp();
  const known = PAGES.find(([to]) => to === loc.pathname);
  const Page = known ? known[3] : NotFound;
  useEffect(() => {
    const t = PAGES.find(([to]) => to === loc.pathname);
    document.title = t ? `${t[1]} · BeaconSpace` : "BeaconSpace";
    window.scrollTo(0, 0);
  }, [loc.pathname]);
  const attrib = run ? run.attribution : null;
  return (
    <>
      <Nav th={th} />
      <main className="page" id="main">
        <div className="bs-hero">
          <div className="bs-brand"><Logo /><h1>BeaconSpace</h1></div>
          <p className="bs-tag">Satellite flood-damage mapping for rescue teams: where the flood hit, what was damaged, and who is cut off.</p>
        </div>
        {runs.length > 0 && !onNew && (
          <>
            <div className="cols pick">
              <div className="sp" />
              <div className="field">
                <label htmlFor="run-pick">Run</label>
                <select id="run-pick" className="inp" value={sel || ""} onChange={(e) => setSel(e.target.value)}>
                  {runs.map((r) => <option key={r.name} value={r.name}>{r.title}</option>)}
                </select>
              </div>
              <div className="sp" />
            </div>
            {run && !runLoading && <Strip S={run.summary} />}
            {run && !runLoading && seasonWarning(run.summary) && <div className="bs-note" style={{ marginBottom: 24 }}>{seasonWarning(run.summary)}</div>}
          </>
        )}
        {runLoading && !onNew ? <Skeleton /> : runError && !onNew ? (
          <div className="bs-empty"><h3 className="bs-head">Could not load this run</h3><p>{runError}</p></div>
        ) : runsLoaded ? <ErrorBoundary key={loc.pathname}><Page /></ErrorBoundary> : <Skeleton />}
        <div className="bs-foot">{(attrib || DEFAULT_ATTRIB).join(" ")}</div>
      </main>
    </>
  );
}

const DEFAULT_ATTRIB = [
  "Contains modified Copernicus Sentinel data 2026.",
  "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.",
  "© OpenStreetMap contributors.",
];

export default function App() {
  const th = useTheme();
  const [runs, setRuns] = useState([]);
  const [runsLoaded, setRunsLoaded] = useState(false);
  const [sel, setSelState] = useState(store.get("bs-run"));
  const [run, setRun] = useState(null);
  const [runLoading, setRunLoading] = useState(false);
  const [runError, setRunError] = useState(null);

  const refresh = useCallback(async (pick) => {
    try {
      const rs = await api("/api/runs");
      setRuns(rs);
      setSelState((cur) => {
        const want = pick || cur;
        return rs.some((r) => r.name === want) ? want : rs[0]?.name || null;
      });
    } catch (e) {
      setRuns([]);
    } finally {
      setRunsLoaded(true);
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const setSel = useCallback((n) => { setSelState(n); store.set("bs-run", n); }, []);

  useEffect(() => {
    if (!sel) { setRun(null); return; }
    let live = true;
    setRunLoading(true); setRunError(null);
    api(`/api/runs/${encodeURIComponent(sel)}`)
      .then((d) => { if (live) { setRun(d); setRunLoading(false); } })
      .catch((e) => { if (live) { setRunError(e.message); setRunLoading(false); } });
    return () => { live = false; };
  }, [sel]);

  const value = useMemo(() => ({ runs, runsLoaded, sel, setSel, run, runLoading, runError, refresh, theme: th.theme }),
    [runs, runsLoaded, sel, setSel, run, runLoading, runError, refresh, th.theme]);

  return (
    <Ctx.Provider value={value}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="*" element={<Shell th={th} />} />
        </Routes>
      </BrowserRouter>
    </Ctx.Provider>
  );
}

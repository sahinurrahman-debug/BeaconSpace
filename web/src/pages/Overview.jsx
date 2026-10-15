import { useApp } from "../ctx.js";
import { Badge, Card, Empty, nf } from "../ui.jsx";
import { GoNew } from "./NoRun.jsx";

function AccessList({ rows, status, cap = 7 }) {
  const sel = rows.filter((r) => r.status === status && !String(r.name).toLowerCase().includes("unnamed"))
    .sort((a, b) => b.n_buildings - a.n_buildings).slice(0, cap);
  if (!sel.length) return <div className="bs-sub">No named settlement in this class.</div>;
  return sel.map((r, i) => {
    const after = r.dist_after_km != null ? `${r.dist_after_km} km` : "no route";
    const before = r.dist_before_km != null ? `${r.dist_before_km} km` : "–";
    return (
      <div className="bs-row" key={i}>
        <div className="bd"><Badge status={status} /></div>
        <div>
          <div className="nm">{String(r.name)}</div>
          <div className="tm">{nf(r.n_buildings)} bldg · {before} → {after}<br />{Number(r.lat).toFixed(3)}°N {Number(r.lon).toFixed(3)}°E</div>
        </div>
      </div>
    );
  });
}

const STEPS = [
  ["1 · CHOOSE", "An area and the flood date."],
  ["2 · ANALYSE", "Radar change detection, terrain and OpenStreetMap from before the event."],
  ["3 · ACT", "Flood and debris map, damaged buildings, roads and bridges, and cut-off villages."],
];

export default function Overview() {
  const { run, sel, theme } = useApp();
  if (!run) {
    return (
      <>
        <Empty title="No analysis yet" body="Run the Trishuli case study (26 August 2026) or choose your own area and date. Everything is computed from free Sentinel, elevation and OpenStreetMap data.">
          <div className="bs-steps">{STEPS.map(([b, t]) => <div key={b}><b>{b}</b>{t}</div>)}</div>
        </Empty>
        <div style={{ height: 16 }} />
        <GoNew />
      </>
    );
  }
  const F = run.facts, S = run.summary, rows = S.settlements || [];
  return (
    <>
      <div className="bs-grid">
        <Card label="Flooded / debris" value={nf(F.impact_ha)} unit="ha" delay={1} sub={`${nf(F.flood_ha)} ha water · ${nf(F.debris_ha)} ha debris`} />
        <Card label="Buildings affected" value={nf(F.b_aff)} delay={2} sub={`of ${nf(F.b_total)} mapped · ${nf(F.b_severe)} likely destroyed`} />
        <Card label="Road hit" value={nf(F.road_hit_km)} unit="km" delay={3} sub={`${F.br_hit} of ${F.br_total} bridges hit`} />
        <Card label="Cut off" value={F.n_cut} delay={4} dot="var(--bs-crit)" sub={`${F.n_long} with a much longer route · ${nf(F.b_cut)} buildings`} />
      </div>
      {run.files.map ? (
        <>
          <iframe key={`${sel}-${theme}`} className="embed" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" title="Flood map" style={{ height: 880 }}
            src={`/api/runs/${encodeURIComponent(sel)}/map?theme=${theme}`} />
          <div className="bs-foot cap">Orbital viewport · basemaps are for display only and are not analysis inputs.</div>
        </>
      ) : (
        <Empty art={false} title="The map file is missing" body="This run has no <code>dashboard_map.html</code>. Re-run the analysis to regenerate it." />
      )}
      <div className="bs-twin">
        <div className="bs-card bs-list">
          <div className="bs-label"><span className="bs-dot" style={{ background: "var(--bs-crit)" }} />Critical · cut off ({F.n_cut})</div>
          <div style={{ marginTop: 8 }}><AccessList rows={rows} status="cut_off" /></div>
        </div>
        <div className="bs-card bs-list">
          <div className="bs-label"><span className="bs-dot" style={{ background: "var(--bs-watch)" }} />Watch · longer route ({F.n_long})</div>
          <div style={{ marginTop: 8 }}><AccessList rows={rows} status="longer_route" /></div>
        </div>
      </div>
      <div className="bs-foot">Largest named settlements first. The full list is under <b>Settlements</b>.</div>
    </>
  );
}

import { useMemo, useState } from "react";
import { useApp } from "../ctx.js";
import { Badge, Empty, Field, Icon, ORDER, PageTitle, nf, pillText } from "../ui.jsx";
import { NoRun } from "./NoRun.jsx";

export default function Settlements() {
  const { run, sel } = useApp();
  const [pick, setPick] = useState(["cut_off", "longer_route"]);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(200);
  const rows = run?.summary.settlements || [];
  const df = useMemo(() => {
    const on = pick.length ? pick : ORDER;
    const ql = q.trim().toLowerCase();
    return rows.filter((r) => on.includes(r.status) && (!ql || String(r.name).toLowerCase().includes(ql)))
      .sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || b.n_buildings - a.n_buildings);
  }, [rows, pick, q]);
  if (!run) return <NoRun />;
  const fp = run.summary.flowpath;
  const toggle = (k) => setShown(200) || setPick((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const csv = `/api/runs/${encodeURIComponent(sel)}/settlements.csv?status=${encodeURIComponent((pick.length ? pick : ORDER).join(","))}&q=${encodeURIComponent(q)}`;

  return (
    <>
      <PageTitle title="Settlements" sub="Road access to the nearest hospital or town, before and after the event." />
      {!rows.length ? (
        <Empty title="No settlements found in this area" body="OpenStreetMap had no named places or building clusters here before the event, so there is nothing to assess for road access." />
      ) : (
        <>
          <div className="cols c2">
            <Field label="Show">
              <div className="pills" role="group" aria-label="Show">
                {ORDER.map((k) => <button key={k} className="pill" aria-pressed={pick.includes(k)} onClick={() => toggle(k)}>{pillText(k)}</button>)}
              </div>
            </Field>
            <Field label="Search a settlement" htmlFor="sq">
              <input id="sq" className="inp" placeholder="e.g. Syapru" value={q} onChange={(e) => { setQ(e.target.value); setShown(200); }} />
            </Field>
          </div>
          {!df.length ? (
            <Empty title="Nothing matches these filters" body="Try selecting more statuses or clearing the search box." />
          ) : (
            <>
              <div className="bs-table-wrap bs-enter">
                <table className="bs-table">
                  <thead><tr><th>Settlement</th><th>Level</th><th className="n">Buildings</th><th className="n">Route before → after</th><th className="n">Position</th><th>Was served by</th></tr></thead>
                  <tbody>
                    {df.slice(0, shown).map((r, i) => (
                      <tr key={i}>
                        <td><b>{String(r.name)}</b><div className="m">{String(r.reason ?? "")}</div></td>
                        <td><Badge status={r.status} /></td>
                        <td className="n">{nf(r.n_buildings)}<div className="m">{nf(r.n_buildings_affected)} affected</div></td>
                        <td className="n">{r.dist_before_km != null ? `${r.dist_before_km} km` : "–"} → {r.dist_after_km != null ? `${r.dist_after_km} km` : "no route"}</td>
                        <td className="n">{Number(r.lat).toFixed(3)}°N {Number(r.lon).toFixed(3)}°E</td>
                        <td>{r.dest_before != null ? String(r.dest_before) : "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="caption">{nf(df.length)} settlements match{df.length > shown ? ` (first ${nf(shown)} shown)` : ""}</div>
              {df.length > shown && (
                <div className="cols mid3"><div className="sp" /><button className="btn" onClick={() => setShown((x) => x + 200)}><Icon name="expand_more" />Show 200 more</button><div className="sp" /></div>
              )}
              <div className="cols mid3" style={{ marginTop: 8 }}>
                <div className="sp" />
                <a className="btn" href={csv} download><Icon name="download" />Download as CSV</a>
                <div className="sp" />
              </div>
            </>
          )}
        </>
      )}
      <PageTitle style={{ marginTop: 40 }} title="Flood path downstream" sub="Settlements along the traced valley, in downstream order." />
      {fp && fp.settlements?.length ? (
        <>
          <p className="center" style={{ marginBottom: 16 }}>
            Traced <b className="bs-mono">{fp.length_km} km</b> from the chosen upstream point; <b className="bs-mono">{nf(fp.buildings_in_corridor || 0)}</b> buildings lie in the susceptible corridor.
          </p>
          <div className="bs-table-wrap">
            <table className="bs-table">
              <thead><tr><th>Settlement (downstream order)</th><th className="n">Distance along path</th><th className="n">Buildings</th></tr></thead>
              <tbody>{fp.settlements.slice(0, 60).map((r, i) => <tr key={i}><td>{String(r.name)}</td><td className="n">{r.km_along_path} km</td><td className="n">{nf(r.n_buildings)}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      ) : (
        <Empty title="No flood path traced" body="Tick <b>Trace the flood path from an upstream point</b> on the New analysis page to list the settlements along the valley in downstream order." />
      )}
    </>
  );
}

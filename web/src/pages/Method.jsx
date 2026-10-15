import { useApp } from "../ctx.js";
import { Card, Expander, PageTitle, pct } from "../ui.jsx";
import { NoRun } from "./NoRun.jsx";

export default function Method() {
  const { run } = useApp();
  if (!run) return <NoRun />;
  const S = run.summary;
  const modelTxt = S.model ? S.model.file : "physics only";
  const prov = [...new Set(Object.values(S.osm.provider))].sort().join(", ");
  const pr = S.s1_pairs;
  const nz = S.noise;
  return (
    <>
      <PageTitle title="Method & data" sub="Which satellite passes, detector and map snapshot produced this result." />
      <div className="bs-grid">
        <Card label="Radar (Sentinel-1)" value={pr.length} unit={`track${pr.length !== 1 ? "s" : ""}`} delay={1} sub="Same-orbit pre/post pairs only. Different tracks are never compared pixel by pixel." />
        <Card label="Optical clear sky" value={S.s2 ? pct(S.s2.clear_fraction) : "none"} delay={2}
          sub={S.s2 ? "Cloud-masked Sentinel-2; adds flood-water evidence only where clear." : "No usable cloud-free overlap; radar only."} />
        <Card label="Detector" value={S.model ? "AI + physics" : "Physics"} delay={3} sub={`${modelTxt}; terrain and river-proximity gates always apply.`} />
        <Card label="OpenStreetMap" value={S.osm.snapshot} delay={4} sub={`Pre-event snapshot via ${prov}. No post-event edits are used.`} />
      </div>
      <div className="bs-table-wrap">
        <table className="bs-table">
          <thead><tr><th>Track</th><th className="n">Post-event pass</th><th className="n">Pre-event series</th><th className="n">Baseline</th><th className="n">Coverage</th></tr></thead>
          <tbody>
            {pr.map((p, i) => (
              <tr key={i}>
                <td>RO {p.rel_orbit} · {p.orbit_state}</td>
                <td className="n">{p.post.slice(0, 16).replace("T", " ")}Z</td>
                <td className="n">{p.pre.length} images · latest {p.pre[0].slice(0, 10)}</td>
                <td className="n">{p.baseline_days} d</td>
                <td className="n">{pct(p.post_coverage)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {nz && nz.vv_sigma_db != null && <div className="caption">Noise floor of stable terrain: VV σ {Number(nz.vv_sigma_db).toFixed(2)} dB · VH σ {Number(nz.vh_sigma_db).toFixed(2)} dB.</div>}
      {run.provenance && (
        <div style={{ marginTop: 16 }}>
          <Expander title="Full provenance (parameters, inputs, forbidden inputs used: none)">
            <pre className="json">{JSON.stringify(run.provenance, null, 2)}</pre>
          </Expander>
        </div>
      )}
    </>
  );
}

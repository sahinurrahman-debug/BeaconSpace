import { useApp } from "../ctx.js";
import { Card, Empty, PageTitle, f2, nf, pct } from "../ui.jsx";
import { NoRun } from "./NoRun.jsx";

export default function Ems() {
  const { run, sel } = useApp();
  if (!run) return <NoRun />;
  const E = run.evaluation;
  return (
    <>
      <PageTitle title="Check vs EMSR927" sub="Comparison with the official Copernicus EMS maps. Used for checking only, never as an input." />
      {E ? (
        <>
          {E.extent && typeof E.extent === "object" && (() => {
            const x = E.extent, b = E.buildings || {}, r = E.roads || {}, t = E.extent_with_30m_tolerance || {}, ci = E.extent_95ci_block_bootstrap;
            return (
              <div className="bs-grid">
                <Card label="Overlap with EMS area" value={f2(x.IoU)} delay={1} sub={ci ? `intersection over union · 95% CI ${f2(ci.IoU[0])}–${f2(ci.IoU[1])}` : "intersection over union"} />
                <Card label="Precision · recall" value={`${f2(x.precision)} · ${f2(x.recall)}`} delay={2} sub={`${f2(t.precision)} · ${f2(t.recall)} with 30 m tolerance${ci ? ` · 95% CI precision ${f2(ci.precision[0])}–${f2(ci.precision[1])}, recall ${f2(ci.recall[0])}–${f2(ci.recall[1])}` : ""}`} />
                <Card label="EMS buildings found" value={pct(b.recall || 0)} delay={3} sub={`${nf(b["reference_found_by_us(within 20 m)"] || 0)} of ${nf(b.reference_affected || 0)}`} />
                <Card label="EMS road length covered" value={pct(r.recall || 0)} delay={4} sub={`our precision ${pct(r.precision || 0)} (OSM maps more tracks than EMS assessed)`} />
              </div>
            );
          })()}
          {run.files.eval_images.map((f) => (
            <div className="cols ems" key={f}>
              <div className="sp" />
              <img className="eval" alt={f.replace(".png", "").replace(/_/g, " ")} src={`/api/runs/${encodeURIComponent(sel)}/image/${f}`} />
              <div className="sp" />
            </div>
          ))}
          <div className="bs-note">Copernicus EMS maps are used for <b>checking only</b>. {run.ems_credit}.</div>
        </>
      ) : (
        <Empty title="No reference comparison for this run"
          body="Download the EMSR927 vector products from the Copernicus EMS site into <code>data/reference/emsr927/</code>, then run <code>python scripts/evaluate_emsr927.py --run outputs/&lt;run&gt;</code>. They are used to check results only — never as input." />
      )}
    </>
  );
}

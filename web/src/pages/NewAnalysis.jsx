import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../ctx.js";
import { Check, Empty, Expander, Field, Icon, PageTitle, Progress, api, nf } from "../ui.jsx";

const RES = [10, 20, 40];

const num = (v) => (v === "" || Number.isNaN(Number(v)) ? NaN : Number(v));

function Num({ label, value, onChange, id }) {
  return (
    <Field label={label} htmlFor={id}>
      <input id={id} className="inp" type="number" step="0.0001" value={value} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

export default function NewAnalysis() {
  const nav = useNavigate();
  const { refresh, setSel } = useApp();
  const [presets, setPresets] = useState(null);
  const [key, setKey] = useState("trishuli");
  const [box, setBox] = useState({ w: "", s: "", e: "", n: "" });
  const [date, setDate] = useState("");
  const [time, setTime] = useState("00:00");
  const [resIdx, setResIdx] = useState(1);
  const [pairs, setPairs] = useState(2);
  const [useS2, setUseS2] = useState(true);
  const [useModel, setUseModel] = useState(true);
  const [trace, setTrace] = useState(true);
  const [tlon, setTlon] = useState("85.38");
  const [tlat, setTlat] = useState("28.2");
  const [job, setJob] = useState(null);          // {status, step, steps, lines, run, error, hint, elapsed}
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState(null);
  const [token, setToken] = useState("");
  const timer = useRef(null);

  useEffect(() => { api("/api/presets").then(setPresets).catch(() => setPresets({})); }, []);
  const cfg = presets?._config || { analyze: true, token: false, max_area_km2: 6000 };

  // choosing an area resets the dependent fields (custom keeps the Trishuli numbers as a starting point, like the original form)
  useEffect(() => {
    if (!presets) return;
    const base = presets[key] || presets.trishuli;
    if (!base) return;
    const [w, s, e, n] = base.bbox;
    setBox({ w: String(w), s: String(s), e: String(e), n: String(n) });
    const [d, t] = base.event.split("T");
    setDate(d); setTime(t);
    const tf = base.trace_from || [85.38, 28.2];
    setTlon(String(tf[0])); setTlat(String(tf[1]));
    setTrace(key === "trishuli");
  }, [presets, key]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const w = num(box.w), s = num(box.s), e = num(box.e), n = num(box.n);
  const areaKm2 = Math.abs((e - w) * 111 * 0.88) * Math.abs((n - s) * 111);
  const running = starting || job?.status === "running";
  const boxOk = [w, s, e, n].every((x) => !Number.isNaN(x)) && w < e && s < n;
  const tooBig = boxOk && areaKm2 > cfg.max_area_km2;

  const poll = (id) => {
    api(`/api/jobs/${id}`).then(async (j) => {
      setJob(j);
      if (j.status === "running") { timer.current = setTimeout(() => poll(id), 1200); return; }
      if (j.status === "done") { await refresh(j.run); setSel(j.run); nav("/overview"); }
    }).catch(() => { timer.current = setTimeout(() => poll(id), 2500); });
  };

  const start = async () => {
    setErr(null); setJob(null); setStarting(true);
    try {
      const body = {
        key, bbox: [w, s, e, n], date, time, res: RES[resIdx], pairs, use_s2: useS2, use_model: useModel,
        trace, trace_lon: trace ? num(tlon) : null, trace_lat: trace ? num(tlat) : null,
      };
      const r = await api("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { "X-Token": token } : {}) }, body: JSON.stringify(body) });
      setJob({ status: "running", step: 0, steps: ["Terrain", "Optical", "Radar", "Detect", "OSM", "Damage", "Cut-off", "Flow path", "Report"], lines: ["Starting…"], elapsed: 0 });
      poll(r.id);
    } catch (x) {
      setErr(x.message);
    } finally {
      setStarting(false);
    }
  };

  const keys = presets ? [...Object.keys(presets).filter((k) => k !== "_config"), "custom"] : ["trishuli"];
  const failed = job?.status === "error";
  const hint = failed && job.hint === "same-track"
    ? "Radar needs images <b>before and after</b> the date on the <b>same orbit track</b> — try a different date or a larger area."
    : "Try a smaller area, a coarser resolution (40 m), or run again — remote data servers are sometimes busy.";

  return (
    <>
      <PageTitle title="New analysis" sub="Pick an area and a flood date. Results open on the Overview page when the run finishes." />
      <div className="cols c2 big">
        <div>
          <Field label="Area" htmlFor="area">
            <select id="area" className="inp" value={key} onChange={(ev) => setKey(ev.target.value)} disabled={running}>
              {keys.map((k) => <option key={k} value={k}>{k === "custom" ? "Custom area" : presets?.[k]?.label || k}</option>)}
            </select>
          </Field>
          <Expander title="Bounding box (west, south, east, north)" open={key === "custom"}>
            <div className="cols c2">
              <Num id="w" label="West" value={box.w} onChange={(v) => setBox({ ...box, w: v })} />
              <Num id="e" label="East" value={box.e} onChange={(v) => setBox({ ...box, e: v })} />
              <Num id="s" label="South" value={box.s} onChange={(v) => setBox({ ...box, s: v })} />
              <Num id="n" label="North" value={box.n} onChange={(v) => setBox({ ...box, n: v })} />
            </div>
          </Expander>
          <div className="cols c2">
            <Field label="Flood date (UTC)" htmlFor="d"><input id="d" className="inp" type="date" value={date} onChange={(ev) => setDate(ev.target.value)} /></Field>
            <Field label="Approximate time (UTC)" htmlFor="t"><input id="t" className="inp" type="time" value={time} onChange={(ev) => setTime(ev.target.value)} /></Field>
          </div>
          <div className="caption">Area ≈ {Number.isFinite(areaKm2) ? nf(areaKm2) : "–"} km². Larger areas and first runs take longer; repeats are cached.</div>
        </div>
        <div>
          <Field label="Resolution (m)" help="10 m is sharpest and slowest; 40 m is a quick look.">
            <div className="range">
              <input type="range" min="0" max="2" step="1" value={resIdx} onChange={(ev) => setResIdx(Number(ev.target.value))} aria-label="Resolution in metres" aria-valuetext={`${RES[resIdx]} m`} />
              <div className="ticks">{RES.map((r) => <span key={r}>{r}</span>)}</div>
            </div>
          </Field>
          <Field label="Radar tracks to combine">
            <div className="range">
              <input type="range" min="1" max="3" step="1" value={pairs} onChange={(ev) => setPairs(Number(ev.target.value))} aria-label="Radar tracks to combine" />
              <div className="ticks"><span>1</span><span>2</span><span>3</span></div>
            </div>
          </Field>
          <Check checked={useS2} onChange={setUseS2}>Use Sentinel-2 where the sky is clear</Check>
          <Check checked={useModel} onChange={setUseModel}>Use the trained AI model if present</Check>
          <Check checked={trace} onChange={setTrace}>Trace the flood path from an upstream point</Check>
          {trace && (
            <div className="cols c2">
              <Num id="tlon" label="Upstream lon" value={tlon} onChange={setTlon} />
              <Num id="tlat" label="Upstream lat" value={tlat} onChange={setTlat} />
            </div>
          )}
        </div>
      </div>
      <div className="cols mid3" style={{ marginTop: 8 }}>
        <div className="sp" />
        <button className="btn primary" onClick={start} disabled={running || !boxOk || tooBig || !date || !cfg.analyze}><Icon name="play_arrow" />Run analysis</button>
        <div className="sp" />
      </div>
      <div style={{ height: 16 }} />
      {cfg.token && cfg.analyze && (
        <div className="cols mid3"><div className="sp" /><Field label="Access token" htmlFor="tok"><input id="tok" className="inp" type="password" autoComplete="off" value={token} onChange={(ev) => setToken(ev.target.value)} /></Field><div className="sp" /></div>
      )}
      {!cfg.analyze && <div className="bs-note" style={{ marginBottom: 16 }}>New analyses are switched off on this server, so only the finished runs can be explored. Run BeaconSpace locally to analyse your own area.</div>}
      {tooBig && <div className="caption center">This area is about {nf(areaKm2)} km²; the server accepts at most {nf(cfg.max_area_km2)} km². Choose a smaller box.</div>}
      {!boxOk && <div className="caption center">The bounding box must have west &lt; east and south &lt; north.</div>}
      {err && <Empty title="The analysis could not start" body={`<code>${err.replace(/[<>&]/g, "")}</code>`} />}
      {job && job.status === "running" && <Progress step={job.step} steps={job.steps} lines={job.lines} elapsed={job.elapsed} />}
      {failed && <Empty title="The analysis could not finish" body={`<code>${job.error}</code><br><br>${hint}`} />}
      {!job && !err && <Empty title="Ready when you are" body="Press <b>Run analysis</b>. You will see each step as it runs; results open automatically." />}
    </>
  );
}

import { useNavigate } from "react-router-dom";
import { Empty, Icon } from "../ui.jsx";

export function GoNew({ label = "Open the analysis form" }) {
  const nav = useNavigate();
  return (
    <div className="cols mid3">
      <div className="sp" />
      <button className="btn primary" onClick={() => nav("/new")}>{label}<Icon name="arrow_forward" /></button>
      <div className="sp" />
    </div>
  );
}

export function NoRun() {
  return (
    <>
      <Empty title="No analysis yet" body="Run an analysis first; results from finished runs appear on this page." />
      <div style={{ height: 16 }} />
      <GoNew />
    </>
  );
}

import { useEffect, useRef, useState } from "react";

type Job = {
  job_id: string;
  state: "active" | "stopping" | "finished" | "failed" | "cancelled" | "needs_clarification";
  instruction: string;
  run_id: string | null;
  error: string | null;
  progress?: {
    snapshot: { state: string; reason: string; completed_steps: string[]; attempt_count: number };
    camera_preview?: {
      sequence: number; simulation_seconds: number; camera_source: string;
      images: { camera: string; data_url: string }[];
    } | null;
  } | null;
};
type Status = { configured: boolean; job: Job | null };

export function OperatorPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [instruction, setInstruction] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [connected, setConnected] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    let timer: number;
    async function refresh() {
      const version = generation.current;
      try {
        const response = await fetch("/api/operator", {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]),
        });
        if (!response.ok) throw new Error("Unable to check workflow status.");
        const next = await response.json() as Status;
        if (!controller.signal.aborted && version === generation.current) {
          setStatus(next);
          setConnected(true);
        }
      } catch {
        if (!controller.signal.aborted) setConnected(false);
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(refresh, 1500);
      }
    }
    void refresh();
    return () => {
      mounted.current = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);

  async function act(stopId?: string) {
    if (pending) return;
    generation.current++;
    setPending(true);
    setError("");
    try {
      const response = await fetch(stopId
        ? `/api/operator/jobs/${encodeURIComponent(stopId)}/stop`
        : "/api/operator/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Bimanual-Operator": "1" },
        body: stopId ? undefined : JSON.stringify({ instruction: instruction.trim() }),
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error(`Request declined (HTTP ${response.status}). Check the current job before retrying.`);
      const job = await response.json() as Job;
      if (mounted.current) setStatus({ configured: true, job });
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : "Request failed. Check workflow status before retrying.");
    } finally {
      generation.current++;
      if (mounted.current) setPending(false);
    }
  }
  const job = status?.job;
  const busy = job?.state === "active" || job?.state === "stopping";
  return <section aria-labelledby="operator-heading" className="operator-panel">
    <h2 id="operator-heading">Run a local workflow</h2>
    <p>Experimental learned control. A finished process does not establish successful table setup.</p>
    {!status?.configured ? <p>{status ? "Controls are not configured on this server. You can still inspect recorded runs below." : "Checking controls…"}</p> : <>
      <form onSubmit={event => { event.preventDefault(); void act(); }}>
        <label htmlFor="workflow-instruction">Dinner-table instruction</label>
        <textarea id="workflow-instruction" value={instruction} maxLength={4096}
          onChange={event => setInstruction(event.target.value)} disabled={busy || pending}
          placeholder="Describe the supported step you want the arms to perform." />
        <button type="submit" disabled={!connected || busy || pending || !instruction.trim()}>Start workflow</button>
      </form>
      {job && <div aria-live="polite">
        <p>Process: <strong>{job.state.replaceAll("_", " ")}</strong></p>
        <p>{job.instruction}</p>
        {job.progress && <div>
          <p>Last worker update (unverified): {job.progress.snapshot.state.replaceAll("_", " ")}</p>
          <p>{job.progress.snapshot.reason}</p>
          <p>Steps reported complete: {job.progress.snapshot.completed_steps.join(", ") || "none"}.
            Attempts: {job.progress.snapshot.attempt_count}.</p>
        </div>}
        {job.progress?.camera_preview && <div>
          <p>Last camera capture: simulation {job.progress.camera_preview.simulation_seconds.toFixed(2)} s,
            frame {job.progress.camera_preview.sequence}. Source: {job.progress.camera_preview.camera_source.replaceAll("_", " ")}.</p>
          <p>These previews may remain unchanged while planning or after stopping.</p>
          <div className="operator-cameras">
            {job.progress.camera_preview.images.map(image => <figure key={image.camera}>
              <img src={image.data_url} alt={`Last worker capture: ${image.camera}`} width={480} height={270} />
              <figcaption>{image.camera.replaceAll("/", " ").replaceAll("_", " ")}</figcaption>
            </figure>)}
          </div>
        </div>}
        {job.error && <p role="alert">{job.error}</p>}
        {job.run_id && <p>Recorded run: <code>{job.run_id}</code>. Refresh run evidence below to inspect the outcome.</p>}
        {busy && <button disabled={pending || job.state === "stopping"} onClick={() => void act(job.job_id)}>
          {job.state === "stopping" ? "Waiting for worker to stop…" : "Stop workflow"}
        </button>}
      </div>}
    </>}
    {!connected && <p role="status">Status connection unavailable. A running job may still be active.</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}

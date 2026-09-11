import { useEffect, useRef, useState } from "react";

type Job = {
  job_id: string;
  state: "active" | "stopping" | "finished" | "failed" | "cancelled";
  instruction: string;
  run_id: string | null;
  error: string | null;
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
        <p>Process: <strong>{job.state}</strong></p>
        <p>{job.instruction}</p>
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

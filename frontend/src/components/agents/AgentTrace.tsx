import type { AssistantResponse } from "../../types/api";

export function AgentTrace({ result }: { result: AssistantResponse }) {
  return (
    <details className="trace-panel">
      <summary>
        <span>Agent trace</span>
        <span className={`review-badge ${result.review.status}`}>
          {result.review.status} · {result.review.retryCount} retries
        </span>
      </summary>
      <div className="trace-timeline">
        {result.trace.map((step, index) => (
          <div className="trace-step" key={`${step.id}-${index}`}>
            <span className={`trace-node ${step.status}`} />
            <div><strong>{step.label}</strong><p>{step.detail}</p></div>
            <time>{step.durationMs} ms</time>
          </div>
        ))}
      </div>
      <div className="run-id">
        Run {result.runId} · {result.usage.totalTokens.toLocaleString()} tokens
      </div>
    </details>
  );
}

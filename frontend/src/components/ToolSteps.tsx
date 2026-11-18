import type { ToolStep } from "../types";

/** The tool calls made during a turn, collapsed by default. */
export function ToolSteps({ steps }: { steps: ToolStep[] }) {
  if (steps.length === 0) return null;
  return (
    <details className="steps">
      <summary>
        {steps.length} tool {steps.length === 1 ? "call" : "calls"}
      </summary>
      {steps.map((step) => (
        <div className="step" key={step.id}>
          <b>{step.name}</b>
          <span className={`tag ${step.status ?? ""}`}>{step.status ?? "running"}</span>
          <code>args: {JSON.stringify(step.args)}</code>
          {step.result !== undefined && <code>result: {JSON.stringify(step.result, null, 1)}</code>}
        </div>
      ))}
    </details>
  );
}

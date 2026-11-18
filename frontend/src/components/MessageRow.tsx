import type { ChatRow } from "../types";
import { Citations } from "./Citations";
import { ToolSteps } from "./ToolSteps";

export function MessageRow({ row }: { row: ChatRow }) {
  if (row.role === "user") {
    return (
      <div className="row user">
        <div className="bubble">{row.text}</div>
      </div>
    );
  }
  const bubble = ["bubble", row.error && "error", row.streaming && "cursor"].filter(Boolean).join(" ");
  return (
    <div className="row">
      <ToolSteps steps={row.steps} />
      <div className={bubble}>{row.text || (row.streaming ? "" : "…")}</div>
      <Citations citations={row.citations} />
    </div>
  );
}

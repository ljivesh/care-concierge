import type { Citation } from "../types";

/** The document sections an answer cites, listed under it. */
export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <ul className="cites">
      {citations.map((citation) => (
        <li key={citation.n}>
          <b>[{citation.n}]</b> {citation.heading_path}
        </li>
      ))}
    </ul>
  );
}

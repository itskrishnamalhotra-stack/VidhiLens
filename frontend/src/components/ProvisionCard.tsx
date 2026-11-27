import { useState } from "react";
import type { Provision } from "../types";
import { Icon } from "./Icon";

export function ProvisionCard({ provision }: { provision: Provision }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article className={`provision-card ${expanded ? "is-expanded" : ""}`}>
      <button className="provision-card__summary" onClick={() => setExpanded((value) => !value)}>
        <span className="provision-id">{provision.provision_id.replace("_", " § ")}</span>
        <span className="provision-title">{provision.title}</span>
        <span className="verified-chip"><Icon name="check" /> In force</span>
        <Icon name="chevron" className="provision-chevron" />
      </button>
      {expanded && (
        <div className="provision-card__detail">
          <p>{provision.verified_text}</p>
          <a href={provision.source_url} target="_blank" rel="noreferrer">
            Open official source{provision.source_pdf_page ? ` · page ${provision.source_pdf_page}` : ""}
            <Icon name="external" />
          </a>
        </div>
      )}
    </article>
  );
}

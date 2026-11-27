import type { AppUser } from "../auth";
import type { Session } from "../types";
import { Icon } from "./Icon";

interface Props {
  user: AppUser;
  sessions: Session[];
  activeSessionId: string | null;
  open: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSettings: () => void;
  onLogout: () => void;
  onClose: () => void;
  onRemove: (id: string) => void;
  onCases: () => void;
  isReviewer: boolean;
}

function relativeDate(value: string) {
  const date = new Date(value);
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function Sidebar(props: Props) {
  return (
    <aside className={`sidebar ${props.open ? "is-open" : ""}`}>
      <div className="sidebar-head">
        <div className="brand">
          <div className="brand-mark"><span>वि</span></div>
          <div><strong>VidhiLens</strong><small>{props.isReviewer ? "Reviewer workspace" : "Legal guidance"}</small></div>
        </div>
        <button className="icon-button sidebar-close" onClick={props.onClose} aria-label="Close menu"><Icon name="close" /></button>
      </div>
      <button className="new-chat" onClick={props.onNew}><Icon name="chat" /> {props.isReviewer ? "New research chat" : "New chat"}</button>
      <button className="sidebar-cases" onClick={props.onCases}><Icon name="file" /> {props.isReviewer ? "Reports" : "My cases"}</button>
      <div className="sidebar-label">{props.isReviewer ? "Research conversations" : "Your conversations"}</div>
      <nav className="session-list" aria-label="Conversations">
        {props.sessions.length === 0 && <p className="empty-list">Your conversations will appear here.</p>}
        {props.sessions.map((session) => (
          <div className={`session-item ${props.activeSessionId === session.session_id ? "active" : ""}`} key={session.session_id}>
            <button onClick={() => props.onSelect(session.session_id)}><Icon name="chat" />
              <span><strong>{session.title}</strong><small>{relativeDate(session.updated_at)}</small></span>
            </button>
            <button className="session-remove" aria-label={`Remove ${session.title}`} title="Delete or archive"
              onClick={() => props.onRemove(session.session_id)}><Icon name="trash" /></button>
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <div className="user-card">
          {props.user.photoURL ? <img src={props.user.photoURL} alt="" /> : <div className="avatar">{props.user.displayName.slice(0, 1).toUpperCase()}</div>}
          <span><strong>{props.user.displayName}</strong><small>{props.user.mode === "firebase" ? "Private account" : "Demo session"}</small></span>
        </div>
        <div className="sidebar-tools">
          <button onClick={props.onSettings}><Icon name="settings" /> Settings</button>
          <button onClick={props.onLogout}><Icon name="logout" /> Sign out</button>
        </div>
      </div>
    </aside>
  );
}

import { useEffect, useRef, useState, type ReactNode } from "react";
import { formatDate, timeAgo } from "../api";
import Icon, { type IconName } from "./Icon";

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className={`alert ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <Icon name={kind === "error" ? "alert" : kind === "success" ? "check" : "sparkles"} />
      <div>{children}</div>
    </div>
  );
}

export function Badge({ tone = "neutral", children, title }: { tone?: "neutral" | "green" | "red" | "blue" | "amber"; children: ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

export function StatusBadge({ active }: { active: boolean }) {
  return active ? <Badge tone="green">Active</Badge> : <Badge tone="red">Disabled</Badge>;
}

export function PageHeader({ title, subtitle, actions, back }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        {back && <div className="back">{back}</div>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

const AVATAR_TONES = 8;

function hash(s: string): number {
  let h = 0;
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h;
}

export function initials(name: string): string {
  const words = name.trim().split(/[\s._-]+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export function Avatar({ name, size = 32, square = false }: { name: string; size?: number; square?: boolean }) {
  return (
    <span
      className={`avatar tone-${hash(name) % AVATAR_TONES}${square ? " square" : ""}`}
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      aria-hidden="true"
    >
      {initials(name)}
    </span>
  );
}

export function TimeAgo({ value }: { value: string | null }) {
  return <time title={formatDate(value)}>{timeAgo(value)}</time>;
}

export function EmptyState({ icon = "inbox", title, children }: { icon?: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={22} /></div>
      <div className="empty-title">{title}</div>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <button
      type="button"
      className="btn small ghost icon-btn"
      title={label}
      aria-label={label}
      onClick={() => navigator.clipboard.writeText(value).then(() => setCopied(true))}
    >
      <Icon name={copied ? "check" : "copy"} size={14} />
    </button>
  );
}

export function CopyField({ value }: { value: string }) {
  return (
    <div className="copy-field">
      <code>{value}</code>
      <CopyButton value={value} />
    </div>
  );
}

export function SecretReveal({ label, value }: { label: string; value: string }) {
  return (
    <div className="secret">
      <div className="secret-label"><Icon name="key" /> {label}</div>
      <CopyField value={value} />
      <p className="muted small">Store this in the system's configuration now. For security it won't be shown again.</p>
    </div>
  );
}

export function PasswordInput({
  value, onChange, onGenerate, autoComplete = "new-password", required, minLength, maxLength, autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  onGenerate?: () => void;
  autoComplete?: string;
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  autoFocus?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="input-group">
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        maxLength={maxLength}
        autoFocus={autoFocus}
      />
      {onGenerate && (
        <button type="button" className="input-addon" title="Generate a strong password" onClick={() => { onGenerate(); setVisible(true); }}>
          <Icon name="sparkles" size={15} />
        </button>
      )}
      <button type="button" className="input-addon" title={visible ? "Hide password" : "Show password"} aria-label={visible ? "Hide password" : "Show password"} onClick={() => setVisible((v) => !v)}>
        <Icon name={visible ? "eyeOff" : "eye"} size={15} />
      </button>
    </div>
  );
}

export function Modal({
  open, title, onClose, children, footer, width = 520,
}: {
  open: boolean;
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: width }} role="dialog" aria-modal="true" ref={ref}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="btn ghost icon-btn" onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={t.id === value} className={t.id === value ? "active" : ""} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Spinner() {
  return <div className="loading"><span className="spinner" /> Loading…</div>;
}

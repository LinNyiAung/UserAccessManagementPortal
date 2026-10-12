import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage, type AuditEntry, type Overview } from "../../api";
import Icon, { type IconName } from "../../components/Icon";
import { Alert, Avatar, Badge, EmptyState, PageHeader, Spinner, TimeAgo } from "../../components/ui";
import { actionTone, describe } from "./AuditPage";

function Stat({ icon, label, value, sub, tone, to }: { icon: IconName; label: string; value: number; sub?: string; tone?: "red"; to?: string }) {
  const body = (
    <>
      <div className={`stat-icon${tone ? ` ${tone}` : ""}`}><Icon name={icon} size={18} /></div>
      <div>
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {sub && <div className="muted small">{sub}</div>}
      </div>
    </>
  );
  return to ? <Link to={to} className="card stat clickable">{body}</Link> : <div className="card stat">{body}</div>;
}

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [recent, setRecent] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get<Overview>("/api/admin/overview"), api.get<AuditEntry[]>("/api/admin/audit?limit=8")])
      .then(([o, a]) => {
        setData(o);
        setRecent(a);
      })
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Spinner />;

  return (
    <>
      <PageHeader title="Overview" subtitle="Accounts, systems and sign-in activity across the company." />

      <div className="stats">
        <Stat icon="users" label="Active users" value={data.users_active} sub={`${data.users_total} total · ${data.admins} admin${data.admins === 1 ? "" : "s"}`} to="/admin/users" />
        <Stat icon="layers" label="Systems" value={data.systems_total} sub="connected via SSO" to="/admin/applications" />
        <Stat icon="key" label="SSO sign-ins" value={data.sso_grants_24h} sub={`last 24h · ${data.sign_ins_24h} portal logins`} to="/admin/audit" />
        <Stat
          icon="alert"
          label="Failed or denied"
          value={data.failed_sign_ins_24h + data.denied_24h}
          sub={`last 24h · ${data.failed_sign_ins_24h} bad password, ${data.denied_24h} no access`}
          tone={data.failed_sign_ins_24h + data.denied_24h > 0 ? "red" : undefined}
          to="/admin/audit"
        />
      </div>

      <div className="two-col">
        <div className="card">
          <div className="card-header">
            <h2>Systems</h2>
            <Link to="/admin/applications" className="small">View all</Link>
          </div>
          {data.systems.length === 0 ? (
            <EmptyState icon="layers" title="No systems yet"><Link to="/admin/applications">Register your first system</Link></EmptyState>
          ) : (
            <ul className="list">
              {data.systems.map((s) => (
                <li key={s.id}>
                  <Link to={`/admin/applications/${s.id}`} className="list-row">
                    <Avatar name={s.name} size={34} square />
                    <div className="grow">
                      <div className="list-title">{s.name} {!s.is_active && <Badge tone="red">Disabled</Badge>}</div>
                      <div className="muted small">{s.role_count} role{s.role_count === 1 ? "" : "s"}</div>
                    </div>
                    <div className="list-metric"><strong>{s.member_count}</strong> <span className="muted small">users</span></div>
                    <Icon name="chevronRight" className="muted" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <h2>Recent activity</h2>
            <Link to="/admin/audit" className="small">Audit log</Link>
          </div>
          {recent.length === 0 ? (
            <EmptyState icon="activity" title="No activity yet" />
          ) : (
            <ul className="timeline">
              {recent.map((e) => {
                const { verb, target } = describe(e);
                return (
                  <li key={e.id}>
                    <span className={`dot ${actionTone(e.action)}`} />
                    <div className="grow">
                      <div>
                        <strong>{e.actor_username || "Someone"}</strong> <span className="muted">{verb}</span> {target}
                      </div>
                      {e.detail && <div className="muted small">{e.detail}</div>}
                    </div>
                    <span className="muted small nowrap"><TimeAgo value={e.created_at} /></span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </>
  );
}

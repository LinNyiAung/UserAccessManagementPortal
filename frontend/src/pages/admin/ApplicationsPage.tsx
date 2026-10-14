import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage, type Application, type ApplicationWithSecret } from "../../api";
import Icon from "../../components/Icon";
import { Alert, Avatar, Badge, EmptyState, Modal, PageHeader, SecretReveal, Spinner } from "../../components/ui";

const emptyForm = { name: "", description: "", home_url: "", redirect_uris: "", web_origins: "", confidential: true };

function originOf(url: string): string | null {
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

/** Browser apps call the portal from their own origin; default to the origins of their redirect URIs. */
function defaultOrigins(redirectUris: string[]): string[] {
  return [...new Set(redirectUris.map(originOf).filter((o): o is string => !!o))];
}

/** Preview of the client ID the portal will generate from the name (the portal adds -2, -3 … if it's taken). */
function clientIdPreview(name: string) {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 90) || "system";
  return base.length < 2 ? `${base}-system` : base;
}

export default function ApplicationsPage() {
  const navigate = useNavigate();
  const [apps, setApps] = useState<Application[] | null>(null);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [formError, setFormError] = useState("");
  const [created, setCreated] = useState<ApplicationWithSecret | null>(null);

  useEffect(() => {
    api.get<Application[]>("/api/admin/applications").then(setApps).catch((e) => setError(errorMessage(e)));
  }, []);

  function openForm() {
    setForm(emptyForm);
    setFormError("");
    setCreated(null);
    setShowForm(true);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError("");
    const redirectUris = form.redirect_uris.split(/\s+/).filter(Boolean);
    const origins = form.web_origins.split(/\s+/).filter(Boolean);
    try {
      const app = await api.post<ApplicationWithSecret>("/api/admin/applications", {
        ...form,
        home_url: form.home_url.trim(),
        redirect_uris: redirectUris,
        web_origins: form.confidential ? origins : origins.length ? origins : defaultOrigins(redirectUris),
      });
      if (app.client_secret) setCreated(app);
      else navigate(`/admin/applications/${app.id}`);
    } catch (err) {
      setFormError(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader
        title="Systems"
        subtitle="Company systems that sign users in through the portal, each with its own roles."
        actions={<button className="btn primary" onClick={openForm}><Icon name="plus" /> Register system</button>}
      />
      <Alert>{error}</Alert>
      {!apps && !error && <Spinner />}

      {apps && apps.length === 0 && (
        <div className="card">
          <EmptyState icon="layers" title="No systems registered">
            Register a system to let users sign in to it with their portal account.
          </EmptyState>
        </div>
      )}

      <div className="system-grid">
        {apps?.map((a) => (
          <Link key={a.id} to={`/admin/applications/${a.id}`} className="card system-card clickable">
            <div className="system-card-head">
              <Avatar name={a.name} size={40} square />
              <div className="grow">
                <h3>{a.name}</h3>
                <code className="small">{a.client_id}</code>
              </div>
              {a.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="red">Disabled</Badge>}
            </div>
            <p className="muted small clamp">{a.description || "No description"}</p>
            <div className="chips">
              {a.roles.slice(0, 5).map((r) => <Badge key={r.id}>{r.name}</Badge>)}
              {a.roles.length > 5 && <Badge>+{a.roles.length - 5}</Badge>}
              {a.roles.length === 0 && <span className="muted small">No roles yet</span>}
            </div>
            <div className="system-card-foot">
              <span><Icon name="users" size={14} /> {a.member_count} user{a.member_count === 1 ? "" : "s"}</span>
              <span><Icon name="shield" size={14} /> {a.permissions.length} permission{a.permissions.length === 1 ? "" : "s"}</span>
              <span><Icon name={a.is_confidential ? "key" : "lock"} size={14} /> {a.is_confidential ? "Client secret" : "Public · PKCE"}</span>
            </div>
          </Link>
        ))}
      </div>

      <Modal
        open={showForm}
        title={created ? "System registered" : "Register a system"}
        onClose={() => (created ? navigate(`/admin/applications/${created.id}`) : setShowForm(false))}
        width={600}
        footer={
          created ? (
            <button className="btn primary" onClick={() => navigate(`/admin/applications/${created.id}`)}>
              I've saved the secret, continue
            </button>
          ) : (
            <>
              <button className="btn" onClick={() => setShowForm(false)}>Cancel</button>
              <button className="btn primary" form="new-system">Register</button>
            </>
          )
        }
      >
        {created ? (
          <>
            <Alert kind="success"><strong>{created.name}</strong> is registered. Next, add its roles and give users access.</Alert>
            <SecretReveal label="Client secret" value={created.client_secret!} />
          </>
        ) : (
          <form id="new-system" className="form-grid" onSubmit={handleCreate}>
            <div className="span-2"><Alert>{formError}</Alert></div>
            <label>
              Name
              <input
                value={form.name}
                required
                autoFocus
                placeholder="e.g. Finance"
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </label>
            <label>
              Client ID
              <input value={form.name.trim() ? clientIdPreview(form.name) : ""} readOnly disabled placeholder="Made from the name" />
              <span className="hint">Generated by the portal from the name and never changes. The system uses it in its sign-in settings.</span>
            </label>
            <label className="span-2">Description<input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="What is this system used for?" /></label>
            <label className="span-2">
              Launch URL
              <input type="url" placeholder="https://finance.company.com/" value={form.home_url} onChange={(e) => setForm({ ...form, home_url: e.target.value })} />
              <span className="hint">Where "Open" on the My apps page takes users.</span>
            </label>
            <label className="span-2">
              Redirect URIs
              <textarea rows={2} placeholder="https://finance.company.com/auth/callback" value={form.redirect_uris} onChange={(e) => setForm({ ...form, redirect_uris: e.target.value })} />
              <span className="hint">One per line. The portal only sends sign-ins back to these exact addresses.</span>
            </label>
            <div className="span-2">
              <div className="label">Client type</div>
              <div className="choice-cards">
                <label className={`choice${form.confidential ? " on" : ""}`}>
                  <input type="radio" name="type" checked={form.confidential} onChange={() => setForm({ ...form, confidential: true })} />
                  <span><strong>Server-side app</strong><span className="hint">Has a backend that can keep a client secret. Most systems.</span></span>
                </label>
                <label className={`choice${!form.confidential ? " on" : ""}`}>
                  <input type="radio" name="type" checked={!form.confidential} onChange={() => setForm({ ...form, confidential: false })} />
                  <span><strong>Browser or mobile app</strong><span className="hint">React, Angular, Vue or mobile. No secret; uses PKCE instead.</span></span>
                </label>
              </div>
            </div>
            {!form.confidential && (
              <label className="span-2">
                Web origins
                <textarea
                  rows={2}
                  placeholder={defaultOrigins(form.redirect_uris.split(/\s+/).filter(Boolean)).join("\n") || "https://finance.company.com"}
                  value={form.web_origins}
                  onChange={(e) => setForm({ ...form, web_origins: e.target.value })}
                />
                <span className="hint">
                  Addresses the app runs on, allowed to call the portal from the browser. One per line, no path.
                  Leave empty to use the redirect URIs' addresses.
                </span>
              </label>
            )}
          </form>
        )}
      </Modal>
    </>
  );
}

import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage, type MyApplication } from "../api";
import { useAuth } from "../auth";
import { useFeedback } from "../components/feedback";
import { Alert, Avatar, Badge, EmptyState, PasswordInput, TimeAgo } from "../components/ui";

export default function ProfilePage() {
  const { user } = useAuth();
  const { toast } = useFeedback();
  const [apps, setApps] = useState<MyApplication[]>([]);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<MyApplication[]>("/api/me/applications").then(setApps).catch(() => {});
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (next !== confirm) return setError("The new passwords don't match.");
    try {
      await api.post("/api/auth/change-password", { current_password: current, new_password: next });
      toast("Password updated");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (!user) return null;
  const name = user.full_name || user.username;
  return (
    <>
      <div className="profile-header">
        <Avatar name={name} size={64} />
        <div>
          <h1>{name}</h1>
          <div className="muted">
            {user.username} · {user.email}
            {user.is_admin && <> · <Badge tone="blue">Portal administrator</Badge></>}
          </div>
        </div>
      </div>

      <div className="two-col">
        <div className="card">
          <h2>My access</h2>
          <p className="muted small">Roles you hold in each system. Contact your administrator to change them.</p>
          {apps.length === 0 ? (
            <EmptyState icon="lock" title="No system access yet" />
          ) : (
            <ul className="access-list">
              {apps.map((a) => (
                <li key={a.id}>
                  <Avatar name={a.name} size={30} square />
                  <span className="access-list-name">{a.name}</span>
                  <span className="chips">{a.roles.map((r) => <Badge key={r} tone="blue">{r}</Badge>)}</span>
                  {a.permissions.length > 0 && (
                    <span className="access-list-perms muted small">Can: {a.permissions.join(", ")}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Last sign-in <TimeAgo value={user.last_login_at} /></p>
        </div>

        <form className="card" onSubmit={handleSubmit}>
          <h2>Change password</h2>
          <p className="muted small">Your password works for every system. At least 8 characters.</p>
          <Alert>{error}</Alert>
          <label>
            Current password
            <PasswordInput value={current} onChange={setCurrent} autoComplete="current-password" required />
          </label>
          <label>
            New password
            <PasswordInput value={next} onChange={setNext} minLength={8} maxLength={72} required />
          </label>
          <label>
            Confirm new password
            <PasswordInput value={confirm} onChange={setConfirm} required />
          </label>
          <button className="btn primary">Update password</button>
        </form>
      </div>
    </>
  );
}

import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import Icon from "../components/Icon";

export default function AccessDeniedPage() {
  const [params] = useSearchParams();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const app = params.get("app");

  async function switchAccount() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="center-page">
      <div className="card narrow">
        <div className="status-icon danger"><Icon name="lock" size={22} /></div>
        <h1>You don't have access</h1>
        <p>
          Your account has no role in <strong>{app || "this system"}</strong>, so the portal can't sign you in to it.
        </p>
        <p className="muted small">Ask your administrator to grant you a role, then try again.</p>
        <Link className="btn primary block" to="/">Go to my apps</Link>
        {user && (
          <p className="muted small center">
            Signed in as <strong>{user.username}</strong> · <button className="link-button" onClick={switchAccount}>Use a different account</button>
          </p>
        )}
      </div>
    </div>
  );
}

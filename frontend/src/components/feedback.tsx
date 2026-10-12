import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import Icon from "./Icon";
import { Modal } from "./ui";

type ToastKind = "success" | "error";
interface Toast { id: number; kind: ToastKind; message: string }

interface ConfirmOptions {
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
}

interface Feedback {
  toast: (message: string, kind?: ToastKind) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const FeedbackContext = createContext<Feedback | null>(null);

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dialog, setDialog] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<(ok: boolean) => void>();
  const nextId = useRef(1);

  const toast = useCallback((message: string, kind: ToastKind = "success") => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 6000 : 3500);
  }, []);

  const confirm = useCallback((options: ConfirmOptions) => {
    setDialog(options);
    return new Promise<boolean>((resolve) => (resolver.current = resolve));
  }, []);

  const close = useCallback((ok: boolean) => {
    resolver.current?.(ok);
    setDialog(null);
  }, []);

  return (
    <FeedbackContext.Provider value={{ toast, confirm }}>
      {children}
      <Modal
        open={!!dialog}
        title={dialog?.title}
        onClose={() => close(false)}
        width={440}
        footer={
          <>
            <button className="btn" onClick={() => close(false)}>Cancel</button>
            <button className={`btn ${dialog?.danger ? "danger solid" : "primary"}`} onClick={() => close(true)} autoFocus>
              {dialog?.confirmLabel ?? "Confirm"}
            </button>
          </>
        }
      >
        <div className="confirm-body">{dialog?.message}</div>
      </Modal>
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <Icon name={t.kind === "success" ? "check" : "alert"} />
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): Feedback {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error("useFeedback must be used inside FeedbackProvider");
  return ctx;
}

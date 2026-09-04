import { Loader2, AlertTriangle, ServerCrash, Inbox } from "lucide-react";

export function LoadingState({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-text-muted text-sm">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-center">
      <AlertTriangle className="h-6 w-6 text-danger" />
      <p className="text-sm text-text-muted max-w-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-border-strong bg-panel-raised px-3 py-1.5 text-xs font-medium text-text hover:border-accent hover:text-accent transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function BackendUnavailableState({ onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <ServerCrash className="h-8 w-8 text-danger" />
      <p className="text-base font-semibold text-text">TrustGraph backend unavailable</p>
      <p className="text-sm text-text-muted max-w-md">
        Could not reach the API. Confirm the backend is running (see backend/README.md) and that
        VITE_API_BASE_URL points at it.
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-border-strong bg-panel-raised px-3 py-1.5 text-xs font-medium text-text hover:border-accent hover:text-accent transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message = "Nothing to show yet." }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center text-text-faint">
      <Inbox className="h-5 w-5" />
      <p className="text-sm">{message}</p>
    </div>
  );
}

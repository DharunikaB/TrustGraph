/**
 * Minimal hash-based "link" -- no react-router dependency. The stack
 * list for M6 doesn't include a router, and three pages don't warrant
 * adding one; plain hash navigation (#/clusters) still gives
 * bookmarkable/shareable URLs without extra dependencies.
 */
export function NavLink({ to, active, onNavigate, children }) {
  return (
    <button
      type="button"
      onClick={() => onNavigate(to)}
      className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? "border-accent text-text"
          : "border-transparent text-text-muted hover:text-text hover:border-border-strong"
      }`}
    >
      {children}
    </button>
  );
}

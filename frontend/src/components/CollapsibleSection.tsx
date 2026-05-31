import { useCallback, useState, type ReactNode } from "react";

type Props = {
  title: string;
  storageKey: string;
  /** true = 접힌 상태(탭만) */
  defaultCollapsed?: boolean;
  count?: number;
  countLabel?: string;
  /** 접힌 때 탭 아래 한 줄 안내 */
  collapsedHint?: string;
  className?: string;
  children: ReactNode;
};

function readCollapsed(key: string, defaultCollapsed: boolean): boolean {
  try {
    const v = localStorage.getItem(key);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  return defaultCollapsed;
}

export default function CollapsibleSection({
  title,
  storageKey,
  defaultCollapsed = false,
  count,
  countLabel = "건",
  collapsedHint,
  className = "",
  children,
}: Props) {
  const [collapsed, setCollapsed] = useState(() =>
    readCollapsed(storageKey, defaultCollapsed)
  );

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(storageKey, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, [storageKey]);

  return (
    <section
      className={`collapsible-section${collapsed ? " is-collapsed" : ""}${
        className ? ` ${className}` : ""
      }`}
    >
      <button
        type="button"
        className="collapsible-tab"
        onClick={toggle}
        aria-expanded={!collapsed}
        title={collapsed ? `${title} 펼치기` : `${title} 접기`}
      >
        <span className="collapsible-chevron" aria-hidden>
          {collapsed ? "▶" : "▼"}
        </span>
        <span className="collapsible-tab-title">{title}</span>
        {count != null && count > 0 && (
          <span className="collapsible-tab-badge">
            {count}
            {countLabel}
          </span>
        )}
        <span className="collapsible-tab-action">
          {collapsed ? "펼치기" : "접기"}
        </span>
      </button>
      {collapsed && collapsedHint ? (
        <p className="collapsible-collapsed-hint">{collapsedHint}</p>
      ) : null}
      {!collapsed && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

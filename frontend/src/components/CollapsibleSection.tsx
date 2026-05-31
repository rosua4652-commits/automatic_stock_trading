import { useCallback, useState, type ReactNode } from "react";

type Props = {
  title: string;
  storageKey: string;
  /** true = 접힌 상태(탭만) */
  defaultCollapsed?: boolean;
  count?: number;
  countLabel?: string;
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
  defaultCollapsed = true,
  count,
  countLabel = "건",
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
      </button>
      {!collapsed && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

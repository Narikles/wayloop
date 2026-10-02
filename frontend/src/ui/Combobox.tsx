import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { useDebounced } from "../lib/ctx";

/** Champ avec suggestions asynchrones (référentiels publics). La saisie libre reste possible. */
export function Combobox<T>({ value, onChange, onPick, search, render, placeholder, footer, minChars = 2, id, icon = true }: {
  value: string;
  onChange: (v: string) => void;
  onPick: (item: T) => void;
  search: (q: string) => Promise<T[]>;
  render: (item: T) => ReactNode;
  placeholder?: string;
  footer?: ReactNode;
  minChars?: number;
  id?: string;
  icon?: boolean;
}) {
  const [items, setItems] = useState<T[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const q = useDebounced(value, 220);
  const listId = useId();
  const box = useRef<HTMLDivElement>(null);
  const picked = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (picked.current) {
      picked.current = false;
      return;
    }
    if (q.trim().length < minChars) {
      setItems([]);
      return;
    }
    let live = true;
    setLoading(true);
    search(q)
      .then((r) => live && (setItems(r), setActive(0), setOpen(document.activeElement === input.current)))
      .catch(() => live && setItems([]))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (it: T) => {
    picked.current = true;
    onPick(it);
    setOpen(false);
  };

  return (
    <div className="combo" ref={box}>
      <div className={icon ? "input-group" : ""}>
        {icon && <Search size={16} />}
        <input
          ref={input}
          id={id}
          className="input"
          value={value}
          placeholder={placeholder}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          autoComplete="off"
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => items.length && setOpen(true)}
          onKeyDown={(e) => {
            if (!open || !items.length) return;
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
            if (e.key === "Enter") { e.preventDefault(); pick(items[active]); }
            if (e.key === "Escape") setOpen(false);
          }}
        />
        {loading && <span className="spinner" style={{ position: "absolute", right: 12, top: 12, color: "var(--subtle)" }} />}
      </div>
      {open && items.length > 0 && (
        <div className="combo-list" id={listId} role="listbox">
          {items.map((it, i) => (
            <div key={i} role="option" aria-selected={i === active} className={`combo-item ${i === active ? "on" : ""}`}
              onMouseDown={(e) => { e.preventDefault(); pick(it); }} onMouseEnter={() => setActive(i)}>
              {render(it)}
            </div>
          ))}
          {footer && <div className="combo-foot">{footer}</div>}
        </div>
      )}
    </div>
  );
}

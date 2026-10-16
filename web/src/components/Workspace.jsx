import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { EmptyState, Icon } from "./Icons.jsx";

// Wide enough for the list and the full card side by side; below it, tiles stack and the chosen one opens in place.
const SIDE_BY_SIDE = "(min-width: 1000px)";

function useSideBySide() {
  const [wide, setWide] = useState(() => (window.matchMedia ? window.matchMedia(SIDE_BY_SIDE).matches : true));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const query = window.matchMedia(SIDE_BY_SIDE);
    const on = (e) => setWide(e.matches);
    query.addEventListener("change", on);
    return () => query.removeEventListener("change", on);
  }, []);
  return wide;
}

// One tab's working area: sub-tabs ("Needs action", "Settled", …), small tiles on the left, the chosen meeting's full
// card on the right. `groups`: [{ id, label, items, empty: { title, text } }]. The parent keeps `group` and `selected`,
// so other parts of the page (the banner's "Start with the first") can point at a meeting.
export default function Workspace({ groups, group, onGroup, selected, onSelect, keyOf, titleOf, renderTile, renderDetail, label }) {
  const wide = useSideBySide();
  const current = groups.find((g) => g.id === group) ?? groups[0];
  const chosen = current.items.find((i) => keyOf(i) === selected) ?? (wide ? current.items[0] : null);
  const chosenKey = chosen ? keyOf(chosen) : null;

  // The meeting you were looking at moved to another group (you just decided it): say where, one click away.
  const [moved, setMoved] = useState(null);
  const last = useRef({ key: null, group: null });
  useEffect(() => {
    const was = last.current;
    if (was.key && was.group === current.id && !current.items.some((i) => keyOf(i) === was.key)) {
      const to = groups.find((g) => g.items.some((i) => keyOf(i) === was.key));
      const item = to?.items.find((i) => keyOf(i) === was.key);
      // the next one opens by itself (on a wide screen the first tile is shown anyway; on a phone, open it)
      const next = current.items[0];
      if (next && !wide) onSelect(keyOf(next));
      setMoved(to && to.id !== current.id
        ? { key: was.key, group: to.id, label: to.label, title: titleOf(item), next: next ? titleOf(next) : null }
        : null);
    }
    last.current = { key: chosenKey, group: current.id };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, current, chosenKey, keyOf, titleOf]);
  useEffect(() => { setMoved(null); }, [group]);

  // On a wide screen the list scrolls on its own, sized to end at the bottom of the window, so the page itself
  // doesn't grow with every meeting (at least room for about three tiles).
  const listRef = useRef(null);
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!wide || !list) return undefined;
    const fit = () => {
      const top = list.getBoundingClientRect().top + window.scrollY;
      list.style.maxHeight = `${Math.max(300, window.innerHeight - top - 16)}px`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [wide, group, current.items.length]);

  function choose(item) {
    onSelect(keyOf(item));
    setMoved(null);
  }

  const tile = (item) => {
    const key = keyOf(item);
    const isChosen = key === chosenKey;
    return (
      <li key={key}>
        <button className={`tile-item ${isChosen ? "chosen" : ""}`} aria-current={isChosen ? "true" : undefined}
          aria-expanded={wide ? undefined : isChosen} onClick={() => (isChosen && !wide ? onSelect("") : choose(item))}>
          {renderTile(item)}
        </button>
        {!wide && isChosen && <div className="tile-open" key={key}>{renderDetail(item)}</div>}
      </li>
    );
  };

  return (
    <section className="workspace" aria-label={label}>
      <div className="subtabs" role="tablist" aria-label={`${label}: groups`}>
        {groups.map((g) => (
          <button key={g.id} role="tab" aria-selected={g.id === current.id} onClick={() => onGroup(g.id)}
            className={g.id === current.id ? "on" : ""}>
            {g.label} <span className={`subtab-count ${g.attention && g.items.length ? "hot" : ""}`}>{g.items.length}</span>
          </button>
        ))}
      </div>

      {moved && (
        <div className="moved-note" role="status">
          <Icon name="check" size={15} /> "{moved.title}" moved to {moved.label}.
          <button className="link" onClick={() => { onGroup(moved.group); onSelect(moved.key); }}>Show it</button>
          {moved.next && <span className="moved-next">Next: <b>{moved.next}</b></span>}
          {!moved.next && current.attention && <span className="moved-next">Nothing else needs action here.</span>}
        </div>
      )}

      {current.items.length === 0 ? (
        <EmptyState title={current.empty.title}>{current.empty.text}</EmptyState>
      ) : wide ? (
        <div className="ws-body">
          <ul className="tile-list scrolls" ref={listRef}>{current.items.map(tile)}</ul>
          <div className="ws-detail">{chosen && <div key={chosenKey}>{renderDetail(chosen)}</div>}</div>
        </div>
      ) : (
        <ul className="tile-list stacked">{current.items.map(tile)}</ul>
      )}
    </section>
  );
}

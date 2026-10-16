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

  // On a wide screen the list sits in a framed box that ends level with the open card on the right (Uma: the page ends
  // where the card and the list end), and scrolls inside it, so the page doesn't grow with every meeting. Re-measured
  // whenever the card changes size; at least room for about two tiles. When more tiles are below, the box's bottom
  // edge fades so it's clear the list goes on.
  const frameRef = useRef(null);
  const listRef = useRef(null);
  const [moreBelow, setMoreBelow] = useState(false);
  const checkMore = () => {
    const list = listRef.current;
    setMoreBelow(!!list && list.scrollTop + list.clientHeight < list.scrollHeight - 2);
  };
  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!wide || !frame) return undefined;
    const detail = frame.closest(".ws-body")?.querySelector(".ws-detail");
    const fit = () => {
      const top = frame.getBoundingClientRect().top;
      const bottom = detail ? detail.getBoundingClientRect().bottom : window.innerHeight - 16;
      frame.style.height = `${Math.max(190, Math.round(bottom - top))}px`;
      checkMore();
    };
    fit();
    const watch = detail && typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    watch?.observe(detail);
    window.addEventListener("resize", fit);
    return () => { watch?.disconnect(); window.removeEventListener("resize", fit); };
  }, [wide, group, current.items.length, chosenKey]);

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
          <div className={`tile-frame ${moreBelow ? "more-below" : ""}`} ref={frameRef}>
            <ul className="tile-list scrolls" ref={listRef} onScroll={checkMore}>{current.items.map(tile)}</ul>
          </div>
          <div className="ws-detail">{chosen && <div key={chosenKey}>{renderDetail(chosen)}</div>}</div>
        </div>
      ) : (
        <ul className="tile-list stacked">{current.items.map(tile)}</ul>
      )}
    </section>
  );
}

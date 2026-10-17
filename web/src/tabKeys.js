// Arrow keys for a row of tabs (the standard tab pattern): Left/Right move to the previous/next tab and open it,
// Home/End go to the first/last. Only the open tab is in the Tab-key order; the arrows reach the others.
export function onTabKey(e, ids, current, choose, domId) {
  const i = ids.indexOf(current);
  let next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: ids.length - 1 }[e.key];
  if (next === undefined) return;
  e.preventDefault();
  next = (next + ids.length) % ids.length;
  choose(ids[next]);
  document.getElementById(domId(ids[next]))?.focus();
}

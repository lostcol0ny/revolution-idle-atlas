import { useMemo, useState, type JSX, type MouseEvent } from 'react';
import type { GraphIndex } from '../graph/adjacency';
import { buildOverview, type OverviewEdge } from '../graph/overview';
import { systemColour, systemIcon } from '../graph/palette';
import { toSearch } from '../graph/urlState';
import './overview.css';

const BOX_W = 150;
const BOX_H = 52;

interface Point {
  x: number;
  y: number;
}

interface Placed {
  /** Each link as a quadratic curve: start, control, end. */
  edges: { edge: OverviewEdge; start: Point; control: Point; end: Point }[];
  boxes: Map<string, Point>;
  width: number;
  height: number;
}

// Below this many boosts, a purely guessed link is hidden until the reader asks
// for it: drawing every pair buries the structure.
const MIN_GUESSED_SHOWN = 3;

// With nothing highlighted, only the heaviest links carry a number.
const LABEL_MIN = 10;

// Systems sit on an ellipse in declared (progression) order, with links as
// chords bowed toward the centre. The system graph is dense and full of
// cycles, which a layered layout turns into a tall tangle of long bypass
// routes; a ring keeps every system the same size, fits the page width, and
// lets related neighbours sit side by side.
function place(systems: { id: string }[], edges: OverviewEdge[]): Placed {
  const width = 1000;
  const height = 760;
  const centre = { x: width / 2, y: height / 2 };
  const rx = width / 2 - BOX_W / 2 - 8;
  const ry = height / 2 - BOX_H / 2 - 8;
  const boxes = new Map<string, Point>(
    systems.map((s, i) => {
      const angle = -Math.PI / 2 + (2 * Math.PI * i) / systems.length;
      return [s.id, { x: centre.x + rx * Math.cos(angle), y: centre.y + ry * Math.sin(angle) }];
    }),
  );

  // Where the ray from a box's centre toward `toward` leaves the box.
  const exit = (box: Point, toward: Point): Point => {
    const dx = toward.x - box.x;
    const dy = toward.y - box.y;
    const scale = Math.min((BOX_W / 2 + 4) / Math.abs(dx || 1e-9), (BOX_H / 2 + 4) / Math.abs(dy || 1e-9));
    return { x: box.x + dx * scale, y: box.y + dy * scale };
  };

  const placed = edges.flatMap((edge) => {
    const a = boxes.get(edge.from);
    const b = boxes.get(edge.to);
    if (a === undefined || b === undefined) return [];
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    // Bow toward the centre, and to the right of travel so A→B and B→A part.
    const control = {
      x: mid.x + (centre.x - mid.x) * 0.35 + ((b.y - a.y) / len) * 28,
      y: mid.y + (centre.y - mid.y) * 0.35 - ((b.x - a.x) / len) * 28,
    };
    return [{ edge, start: exit(a, control), control, end: exit(b, control) }];
  });
  return { edges: placed, boxes, width, height };
}

const strokeWidth = (total: number) => Math.min(1 + Math.log2(total) * 1.1, 8);

function linkTitle(e: OverviewEdge, names: Map<string, string>): string {
  const plural = e.total === 1 ? 'boost' : 'boosts';
  return `${names.get(e.from)} boosts ${names.get(e.to)}: ${e.total} ${plural} (${e.established} established, ${e.uncertain} guessed)`;
}

export function Overview(props: { index: GraphIndex; onSelectSystem: (id: string) => void }): JSX.Element {
  const { index, onSelectSystem } = props;
  const overview = useMemo(() => buildOverview(index), [index]);
  const [showAll, setShowAll] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const shown = useMemo(
    () => (showAll ? overview.edges : overview.edges.filter((e) => e.established > 0 || e.total >= MIN_GUESSED_SHOWN)),
    [overview, showAll],
  );
  const placed = useMemo(() => place(overview.systems, shown), [overview, shown]);
  const names = useMemo(() => new Map(overview.systems.map((s) => [s.id, s.name])), [overview]);

  return (
    <div className="overview">
      <section className="overview-intro">
        <h1>Revolution Idle Atlas</h1>
        <p>
          A map of how Revolution Idle's systems and upgrades feed each other: what boosts what, what unlocks
          what, and what each item requires. It is built from the community wiki and the game's own text. Links
          we could not confirm are marked as guessed and drawn faint, so treat them as leads rather than facts.
          Pick a system below to see its items, or open any item to follow its connections.
        </p>
      </section>

      <section className="overview-map" aria-labelledby="overview-map-title">
        <h2 id="overview-map-title">How the systems connect</h2>
        <p className="overview-legend">
          An arrow from one system to another means items in the first boost items in the second; the number
          counts those boosts, and thicker means more. Point at or tab to a system to see only its links and their
          counts. <span className="overview-legend-faint">Faint lines</span> are made only of guessed boosts.
        </p>
        <label className="overview-toggle">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show all links
          {showAll ? '' : ` (${overview.edges.length - shown.length} guessed links with fewer than ${MIN_GUESSED_SHOWN} boosts hidden)`}
        </label>
        <div className="overview-scroll">
          <svg
            viewBox={`0 0 ${placed.width} ${placed.height}`}
            role="group"
            aria-label="System connection map"
          >
            <defs>
              <marker
                id="ov-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="10"
                markerHeight="10"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path d="M0,0 L10,5 L0,10 z" fill="var(--muted)" />
              </marker>
            </defs>
            {placed.edges.map(({ edge, start, control, end }) => {
              const related = focus !== null && (edge.from === focus || edge.to === focus);
              const d = `M${start.x},${start.y} Q${control.x},${control.y} ${end.x},${end.y}`;
              const mid = { x: (start.x + 2 * control.x + end.x) / 4, y: (start.y + 2 * control.y + end.y) / 4 };
              const classes = ['ov-edge'];
              if (edge.established === 0) classes.push('ov-edge-faint');
              if (focus !== null) classes.push(related ? 'ov-edge-on' : 'ov-edge-dim');
              const labelled = focus === null ? edge.total >= LABEL_MIN : related;
              return (
                <g key={`${edge.from}>${edge.to}`} className={classes.join(' ')}>
                  <title>{linkTitle(edge, names)}</title>
                  <path d={d} strokeWidth={strokeWidth(edge.total)} markerEnd="url(#ov-arrow)" />
                  {labelled && (
                    <text x={mid.x} y={mid.y} textAnchor="middle" dominantBaseline="central" aria-hidden="true">
                      {edge.total}
                    </text>
                  )}
                </g>
              );
            })}
            {overview.systems.map((s) => {
              const at = placed.boxes.get(s.id);
              if (at === undefined) return null;
              // Same contract as App's NavLink: a real link that navigates in place on a plain click.
              const onClick = (event: MouseEvent<Element>) => {
                if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                onSelectSystem(s.id);
              };
              return (
                <g key={s.id} transform={`translate(${at.x - BOX_W / 2},${at.y - BOX_H / 2})`}>
                <a
                  className="ov-node"
                  href={`${window.location.pathname}${toSearch({ nodeId: null, systemId: s.id, depth: null })}`}
                  aria-label={`${s.name}, ${s.count} items`}
                  onClick={onClick}
                  onMouseEnter={() => setFocus(s.id)}
                  onMouseLeave={() => setFocus(null)}
                  onFocus={() => setFocus(s.id)}
                  onBlur={() => setFocus(null)}
                >
                  <rect width={BOX_W} height={BOX_H} rx={8} style={{ stroke: systemColour(s.id) }} />
                  <text x={10} y={25} className="ov-node-name">
                    {systemIcon(s.id)} {s.name}
                  </text>
                  <text x={10} y={46} className="ov-node-count">
                    {s.count} items
                  </text>
                </a>
                </g>
              );
            })}
          </svg>
        </div>
        <details className="overview-links">
          <summary>Links as a table</summary>
          <table>
            <caption>Boosts between systems{showAll ? '' : ', as drawn on the map'}</caption>
            <thead>
              <tr>
                <th scope="col">From</th>
                <th scope="col">To</th>
                <th scope="col">Boosts</th>
                <th scope="col">Guessed</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((e) => (
                <tr key={`${e.from}>${e.to}`}>
                  <td>{names.get(e.from)}</td>
                  <td>{names.get(e.to)}</td>
                  <td>{e.total}</td>
                  <td>{e.uncertain}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <section aria-labelledby="overview-cards-title">
        <h2 id="overview-cards-title">All systems</h2>
        <ul className="overview-cards" role="list">
          {overview.systems.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                className="overview-card"
                style={{ borderLeftColor: systemColour(s.id) }}
                onClick={() => onSelectSystem(s.id)}
              >
                <span className="overview-card-icon" aria-hidden="true">
                  {systemIcon(s.id)}
                </span>
                <span className="overview-card-name">{s.name}</span>
                <span className="overview-card-count">{s.count} items</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

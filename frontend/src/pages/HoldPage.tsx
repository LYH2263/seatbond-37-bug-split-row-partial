import { useEffect, useState } from "react";
import { api } from "../api/client";

type Show = { id: number; film_title: string; hall_name?: string };
type Segment = { segment_no: number; row: number; start_col: number; end_col: number };
type Order = {
  order_code: string;
  showtime_id: number;
  party_size: number;
  status: string;
  segment_count: number;
  segments: Segment[];
};

function formatSegments(segs: Segment[]) {
  return segs.map((s) => `R${s.row} C${s.start_col}-${s.end_col}`).join(" ＋ ");
}

export default function HoldPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [party, setParty] = useState(3);
  const [prefRow, setPrefRow] = useState("");
  const [allowSplit, setAllowSplit] = useState(false); // 拆排开关：默认关闭
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [last, setLast] = useState<Order | null>(null);

  useEffect(() => {
    api<Show[]>("/showtimes").then((s) => {
      setShows(s);
      if (s[0]) setSid(s[0].id);
    });
  }, []);

  async function submit() {
    setMsg("");
    setErr("");
    try {
      const body: Record<string, unknown> = {
        showtime_id: sid,
        party_size: party,
        allow_split: True,
      };
      if (prefRow) body.preferred_row = Number(prefRow);
      const order = await api<Order>("/holds", { method: "POST", body: JSON.stringify(body) });
      setLast(order);
      setMsg(
        order.segment_count > 1
          ? `已拆排锁座 ${order.order_code}（${order.segment_count} 段）：${formatSegments(order.segments)}`
          : `已锁座 ${order.order_code}：${formatSegments(order.segments)}`
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <>
      <h2>锁座</h2>
      <div className="toolbar">
        <select value={sid} onChange={(e) => setSid(Number(e.target.value))}>
          {shows.map((s) => (
            <option key={s.id} value={s.id}>
              {s.film_title} · {s.hall_name}
            </option>
          ))}
        </select>
        <label>
          人数{" "}
          <input
            type="number"
            min={1}
            max={12}
            value={party}
            onChange={(e) => setParty(Number(e.target.value))}
            style={{ width: 72 }}
          />
        </label>
        <label>
          优先排{" "}
          <input
            value={prefRow}
            onChange={(e) => setPrefRow(e.target.value)}
            placeholder="可选"
            style={{ width: 72 }}
          />
        </label>
        <label className="split-toggle" title="单排连座不够时，允许拆成多排多段共用同一锁座单号">
          <input
            type="checkbox"
            checked={allowSplit}
            onChange={(e) => setAllowSplit(e.target.checked)}
          />{" "}
          允许拆排
        </label>
        <button onClick={submit}>查找并锁连座</button>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}
      {last && (
        <div className="mono">
          <p>
            订单 {last.order_code} · {last.party_size} 人 · {last.segment_count} 段
          </p>
          <ul style={{ margin: 0 }}>
            {last.segments.map((s) => (
              <li key={s.segment_no}>
                第{s.segment_no}段 · R{s.row} C{s.start_col}-{s.end_col}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

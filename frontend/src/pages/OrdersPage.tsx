import { useEffect, useState } from "react";
import { api } from "../api/client";

type Segment = { segment_no: number; row: number; start_col: number; end_col: number };
type Order = {
  order_code: string;
  showtime_id: number;
  party_size: number;
  status: string;
  segment_count: number;
  segments: Segment[];
};

export default function OrdersPage() {
  const [rows, setRows] = useState<Order[]>([]);
  useEffect(() => {
    api<Order[]>("/holds/orders").then(setRows);
  }, []);
  return (
    <>
      <h2>订单</h2>
      <table className="table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>场次</th>
            <th>座位段</th>
            <th>段数</th>
            <th>人数</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={`${o.order_code}-${o.showtime_id}`}>
              <td className="mono">{o.order_code}</td>
              <td>{o.showtime_id}</td>
              <td className="mono">
                {o.segments.slice(0, 1).map((s) => (
                  <div key={s.segment_no}>
                    段{s.segment_no} · R{s.row} C{s.start_col}-{s.end_col}
                  </div>
                ))}
              </td>
              <td>{o.segment_count}</td>
              <td>{o.party_size}</td>
              <td>{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

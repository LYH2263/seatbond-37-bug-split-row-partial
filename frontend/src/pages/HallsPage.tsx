import { useEffect, useState } from "react";
import { api } from "../api/client";

type SeatRef = { row: number; col: number };
type Hall = {
  id: number;
  name: string;
  rows: number;
  cols: number;
  aisle_cols: number[];
  blocked_seats: SeatRef[];
  frozen: boolean;
};

export default function HallsPage() {
  const [rows, setRows] = useState<Hall[]>([]);
  useEffect(() => {
    api<Hall[]>("/halls").then(setRows);
  }, []);
  return (
    <>
      <h2>影厅</h2>
      <table className="table">
        <thead>
          <tr>
            <th>名称</th>
            <th>行×列</th>
            <th>过道列</th>
            <th>遮挡禁坐</th>
            <th>厅图状态</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.id}>
              <td>{h.name}</td>
              <td className="mono">
                {h.rows} × {h.cols}
              </td>
              <td className="mono">{h.aisle_cols.join(", ") || "—"}</td>
              <td className="mono">
                {h.blocked_seats.map((s) => `R${s.row}C${s.col}`).join(", ") || "—"}
              </td>
              <td>{h.frozen ? "已冻结" : "可锁座"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

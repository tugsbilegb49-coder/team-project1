import { useEffect, useState } from "react";
import { list } from "./api";

export default function AuditLogs() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    list("/api/audit-logs/")
      .then((data) => { if (active) setRows(data); })
      .catch((failure) => { if (active) setError(failure.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  return (
    <section className="task-section audit-section">
      <header className="header"><h1>Өөрчлөлтийн түүх</h1></header>
      <p>Ажилтан, хэлтэс, monitoring зөвшөөрөлтэй холбоотой сүүлийн өөрчлөлтүүд.</p>
      {loading && <p role="status">Уншиж байна…</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && rows.length === 0 && <p>Бүртгэл одоогоор алга.</p>}
      {rows.length > 0 && (
        <div className="audit-table-wrap">
          <table className="audit-table">
            <thead><tr><th>Огноо</th><th>Үйлдэгч</th><th>Үйлдэл</th><th>Объект</th><th>Өөрчлөлт</th></tr></thead>
            <tbody>{rows.map((row) => (
              <tr key={row.id}>
                <td>{new Date(row.created_at).toLocaleString("mn-MN", { timeZone: "Asia/Ulaanbaatar" })}</td>
                <td>{row.actor_name}</td>
                <td>{row.action}</td>
                <td>{row.entity_type}: {row.target_label}</td>
                <td><code>{JSON.stringify(row.changes)}</code></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

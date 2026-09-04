import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

const LEVEL_COLORS = { CRITICAL: "#dc2626", HIGH: "#f97316", MEDIUM: "#f59e0b", LOW: "#22c55e" };
const ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

/** Bar chart of candidate-cluster counts by M3 risk level -- real data only. */
export default function RiskDistributionChart({ clusters }) {
  const counts = Object.fromEntries(ORDER.map((l) => [l, 0]));
  for (const c of clusters) {
    if (counts[c.risk?.level] !== undefined) counts[c.risk.level] += 1;
  }
  const data = ORDER.map((level) => ({ level, count: counts[level] }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2e38" vertical={false} />
        <XAxis dataKey="level" tick={{ fill: "#9aa1af", fontSize: 11 }} axisLine={{ stroke: "#2a2e38" }} tickLine={false} />
        <YAxis tick={{ fill: "#9aa1af", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: "#1d212b", border: "1px solid #2a2e38", borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: "#e6e8ec" }}
          cursor={{ fill: "#2a2e3855" }}
        />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.level} fill={LEVEL_COLORS[entry.level]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

import { useState, useEffect } from "react"
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, ReferenceLine } from "recharts"

const API = "http://localhost:8000"

function MetricCard({ label, value, sub, color, icon }) {
  return (
    <div style={{
      background: "#0d1117", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px",
      borderLeft: `3px solid ${color}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: "#4a5568", textTransform: "uppercase", letterSpacing: "0.07em", fontWeight: 600 }}>{label}</span>
        {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
      </div>
      <div style={{ fontSize: 22, fontWeight: 800, color, fontFamily: "monospace" }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "#718096", marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function StatusBadge({ status, color }) {
  return (
    <span style={{
      background: color + "22", color, border: `1px solid ${color}`,
      borderRadius: 4, padding: "2px 8px", fontSize: 10, fontWeight: 700,
    }}>{status}</span>
  )
}

export default function SystemHealth() {
  const [sysMetrics, setSysMetrics] = useState({})
  const [modelMetrics, setModelMetrics] = useState({})
  const [latencyHistory, setLatencyHistory] = useState([])
  const [alertHistory, setAlertHistory] = useState([])

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const [s, m] = await Promise.all([
          fetch(`${API}/metrics/system`).then(r => r.json()).catch(() => ({})),
          fetch(`${API}/metrics/model`).then(r => r.json()).catch(() => ({})),
        ])
        setSysMetrics(s)
        setModelMetrics(m)

        const t = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })

        setLatencyHistory(prev =>
          [...prev, { t, latency: s.latency_ms || 0, sla: 200 }].slice(-40)
        )

        setAlertHistory(prev =>
          [...prev, { t, alerts: s.alerts_per_min || 0, fpr: s.fpr || 0 }].slice(-40)
        )

      } catch {}
    }

    fetchMetrics()
    const id = setInterval(fetchMetrics, 3000)
    return () => clearInterval(id)
  }, [])

  const latColor = (sysMetrics.latency_ms || 0) < 200 ? "#22c55e" : (sysMetrics.latency_ms || 0) < 500 ? "#f97316" : "#ef4444"
  const slaStatus = (sysMetrics.sla_breach_pct || 0) < 5
  const driftColor = sysMetrics.drift_status === "Stable" ? "#22c55e" : sysMetrics.drift_status === "Warning" ? "#f97316" : "#ef4444"
  const pressureColor = sysMetrics.fraud_pressure === "HIGH" ? "#ef4444" : sysMetrics.fraud_pressure === "MEDIUM" ? "#f97316" : "#22c55e"

  return (
    <div style={{ height: "100%", overflow: "auto", display: "flex", flexDirection: "column", gap: 14 }}>

      {/* KPI Row 1: Core System Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        <MetricCard label="Throughput" value={`${sysMetrics.tps || 0} tps`}
          sub="transactions per second" color="#00E5FF" icon="⚡" />
        <MetricCard label="P99 Latency" value={`${sysMetrics.latency_ms || 0}ms`}
          sub={`SLA: ${slaStatus ? "✓ OK" : "✗ BREACH"} · breach: ${sysMetrics.sla_breach_pct || 0}%`}
          color={latColor} icon="⏱" />
        <MetricCard label="Alerts / min" value={sysMetrics.alerts_per_min || 0}
          sub="fraud alerts generated" color="#f97316" icon="🚨" />
        <MetricCard label="Kafka Queue" value={sysMetrics.queue_size || 0}
          sub={`alerts buffered: ${sysMetrics.alert_queue_size || 0}`} color="#a78bfa" icon="📬" />
        <MetricCard label="Uptime" value={formatUptime(sysMetrics.uptime || 0)}
          sub="system running" color="#22c55e" icon="🟢" />
      </div>

      {/* KPI Row 2: Model & Risk Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        <MetricCard label="False Positive Rate" value={`${sysMetrics.fpr || 0}%`}
          sub="Target ≤ 1.0%" color={(sysMetrics.fpr || 0) <= 1 ? "#22c55e" : "#ef4444"} icon="📊" />
        <MetricCard label="Fraud Catch Rate" value={`${sysMetrics.recall || 0}%`}
          sub="Target ≥ 85%" color={(sysMetrics.recall || 0) >= 85 ? "#22c55e" : "#ef4444"} icon="🎯" />
        <MetricCard label="Drift Status"
          value={sysMetrics.drift_status || "Stable"}
          sub={`PSI: ${sysMetrics.drift_psi || 0}`}
          color={driftColor} icon="📈" />
        <MetricCard label="Fraud Pressure" value={sysMetrics.fraud_pressure || "LOW"}
          sub="current threat level" color={pressureColor} icon="🔥" />
        <MetricCard label="Gateway Holds" value={sysMetrics.held || 0}
          sub="transactions pending review" color="#eab308" icon="🔒" />
      </div>

      {/* Charts Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>

        {/* Latency Trend */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Inference Latency Trend
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={latencyHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
              <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#4a5568" }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 9, fill: "#4a5568" }} unit="ms" />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
              <ReferenceLine y={200} stroke="#ef4444" strokeDasharray="4 2" label={{ value: "200ms SLA", fill: "#ef4444", fontSize: 9 }} />
              <Line type="monotone" dataKey="latency" stroke="#00E5FF" dot={false} strokeWidth={2} name="P99 Latency" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Alert Rate & FPR */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Alert Volume & FPR Trend
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={alertHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
              <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#4a5568" }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 9, fill: "#4a5568" }} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
              <Line type="monotone" dataKey="alerts" stroke="#f97316" dot={false} strokeWidth={2} name="Alerts/min" />
              <Line type="monotone" dataKey="fpr" stroke="#ef4444" dot={false} strokeWidth={1.5} strokeDasharray="4 2" name="FPR %" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detailed Breakdown Row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>

        {/* Latency Breakdown */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Latency Breakdown
          </div>
          {[
            { label: "Feature Engineering", value: sysMetrics.latency?.feature || 0, color: "#a78bfa", pct: 40 },
            { label: "Model Inference", value: sysMetrics.latency?.model || 0, color: "#38bdf8", pct: 50 },
            { label: "API Overhead", value: sysMetrics.latency?.api || 0, color: "#fb923c", pct: 10 },
          ].map(l => (
            <div key={l.label} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: "#a0aec0" }}>{l.label}</span>
                <span style={{ fontSize: 11, fontWeight: 700, color: l.color, fontFamily: "monospace" }}>{l.value}ms</span>
              </div>
              <div style={{ height: 4, background: "#0d1117", borderRadius: 2 }}>
                <div style={{ height: 4, width: `${l.pct}%`, background: l.color, borderRadius: 2 }} />
              </div>
            </div>
          ))}
          <div style={{ marginTop: 10, fontSize: 10, color: "#4a5568" }}>
            Total: {sysMetrics.latency_ms || 0}ms · SLA: {slaStatus ? "✓" : "✗"} 200ms
          </div>
        </div>

        {/* Confusion Matrix Summary */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Analyst Decision Summary
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { label: "True Positives", value: modelMetrics.true_positives || 0, color: "#22c55e", desc: "Fraud confirmed" },
              { label: "False Positives", value: modelMetrics.false_positives || 0, color: "#ef4444", desc: "Legit wrongly flagged" },
              { label: "True Negatives", value: modelMetrics.true_negatives || 0, color: "#22c55e", desc: "Legit passed" },
              { label: "False Negatives", value: modelMetrics.false_negatives || 0, color: "#f97316", desc: "Fraud missed" },
            ].map(c => (
              <div key={c.label} style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 6, padding: "8px 10px" }}>
                <div style={{ fontSize: 9, color: "#4a5568", textTransform: "uppercase", marginBottom: 2 }}>{c.label}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: c.color }}>{c.value}</div>
                <div style={{ fontSize: 9, color: "#718096" }}>{c.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* System Status Indicators */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Service Status
          </div>
          {[
            { label: "Kafka Consumer", status: "ACTIVE", color: "#22c55e" },
            { label: "ML Scoring Engine", status: "ACTIVE", color: "#22c55e" },
            { label: "Graph Analyser", status: "ACTIVE", color: "#22c55e" },
            { label: "GenAI Engine", status: "ACTIVE", color: "#22c55e" },
            { label: "Gateway Simulator", status: "ACTIVE", color: "#22c55e" },
            { label: "Redis Cache", status: "ACTIVE", color: "#22c55e" },
          ].map(s => (
            <div key={s.label} style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "6px 0", borderBottom: "1px solid #1e2538",
            }}>
              <span style={{ fontSize: 11, color: "#a0aec0" }}>{s.label}</span>
              <StatusBadge status={s.status} color={s.color} />
            </div>
          ))}
          <div style={{ marginTop: 10, fontSize: 10, color: "#4a5568" }}>
            Prometheus: localhost:9090 · Grafana: localhost:3001
          </div>
        </div>
      </div>

    </div>
  )
}

function formatUptime(seconds) {
  if (!seconds) return "0s"
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}
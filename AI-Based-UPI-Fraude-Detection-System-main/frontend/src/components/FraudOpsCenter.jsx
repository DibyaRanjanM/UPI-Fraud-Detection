import { useState, useEffect, useRef, useCallback } from "react"
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts"
import { useStore } from "../store/useStore"

const API = "http://localhost:8000"

const TIER_STYLE = {
  "Block":      { color: "#ef4444", bg: "#2d1515", border: "#ef4444", label: "BLOCK" },
  "High-Risk":  { color: "#f97316", bg: "#2d1e0f", border: "#f97316", label: "HIGH-RISK" },
  "Suspicious": { color: "#eab308", bg: "#2d2a1a", border: "#eab308", label: "SUSPICIOUS" },
  "Legitimate": { color: "#22c55e", bg: "#1c3829", border: "#22c55e", label: "SAFE" },
}
const tierOf = t => TIER_STYLE[t] || TIER_STYLE["Legitimate"]

function KpiCard({ label, value, sub, color, icon }) {
  return (
    <div style={{
      background: "#0d1117", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px",
      borderLeft: `3px solid ${color}`,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: "#4a5568", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 16 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color, fontFamily: "monospace" }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "#718096", marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function AlertCard({ alert, onAction, isSelected, onSelect }) {
  const tc = tierOf(alert.risk_tier)
  const shap = (alert.shap_top5 || alert.explainability || []).slice(0, 3)
  const elapsed = Math.round((Date.now() / 1000 - (alert.timestamp || 0)))
  const elapsedStr = elapsed > 3600 ? `${Math.floor(elapsed/3600)}h ago` : elapsed > 60 ? `${Math.floor(elapsed/60)}m ago` : `${elapsed}s ago`

  return (
    <div onClick={() => onSelect(alert)} style={{
      background: isSelected ? tc.bg : "#0d1117",
      border: `1px solid ${isSelected ? tc.border : "#30363d"}`,
      borderRadius: 8, padding: "10px 12px", cursor: "pointer",
      transition: "all 0.2s",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{
            background: tc.bg, color: tc.color, border: `1px solid ${tc.border}`,
            borderRadius: 4, padding: "2px 6px", fontSize: 9, fontWeight: 700,
          }}>{tc.label}</span>
          <span style={{ fontSize: 10, fontFamily: "monospace", color: "#718096" }}>{alert.txn_id?.slice(0, 10)}</span>
        </div>
        <span style={{ fontSize: 9, color: "#4a5568" }}>{elapsedStr}</span>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, marginBottom: 6 }}>
        <span style={{ color: "#e2e8f0", fontWeight: 700 }}>₹{Number(alert.amount || 0).toLocaleString("en-IN")}</span>
        <span style={{ color: tc.color, fontWeight: 700, fontFamily: "monospace" }}>{(alert.ensemble_score || 0).toFixed(3)}</span>
      </div>

      {/* Top 3 SHAP features */}
      {shap.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {shap.map((s, i) => (
            <div key={i} style={{ fontSize: 9, color: "#a0aec0", display: "flex", justifyContent: "space-between" }}>
              <span>{s.feature?.replace(/_/g, " ")}</span>
              <span style={{ color: (s.shap || 0) > 0 ? "#ef4444" : "#22c55e", fontFamily: "monospace" }}>
                {(s.shap || 0) > 0 ? "↑" : "↓"}{Math.abs(s.shap || 0).toFixed(3)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Fraud pattern badge */}
      {alert.fraud_flag && alert.fraud_flag !== "LEGIT" && (
        <div style={{ fontSize: 9, color: "#f97316", background: "#2d1e0f", border: "1px solid #f97316", borderRadius: 3, padding: "1px 5px", display: "inline-block", marginBottom: 6 }}>
          {alert.fraud_flag}
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
        <button onClick={e => { e.stopPropagation(); onAction(alert.txn_id, "confirm_fraud") }} style={{
          flex: 1, padding: "5px 0", fontSize: 9, fontWeight: 700, cursor: "pointer",
          background: "#2d1515", color: "#ef4444", border: "1px solid #ef4444", borderRadius: 4,
        }}>✓ Fraud</button>
        <button onClick={e => { e.stopPropagation(); onAction(alert.txn_id, "mark_legitimate") }} style={{
          flex: 1, padding: "5px 0", fontSize: 9, fontWeight: 700, cursor: "pointer",
          background: "#1c3829", color: "#22c55e", border: "1px solid #22c55e", borderRadius: 4,
        }}>✓ Legit</button>
        <button onClick={e => { e.stopPropagation(); onAction(alert.txn_id, "escalate") }} style={{
          flex: 1, padding: "5px 0", fontSize: 9, fontWeight: 700, cursor: "pointer",
          background: "#2d1e0f", color: "#f97316", border: "1px solid #f97316", borderRadius: 4,
        }}>↑ Escalate</button>
      </div>
    </div>
  )
}

export default function FraudOpsCenter() {
  const { analytics, systemMetrics, setAnalytics, setSystemMetrics } = useStore()

  const [txns, setTxns] = useState([])
  const [alerts, setAlerts] = useState([])
  const [selected, setSelected] = useState(null)
  const [explanation, setExplanation] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [modelMetrics, setModelMetrics] = useState(null)

  const buffer = useRef([])
  const explainRef = useRef(null)
  const esRef = useRef(null)

  // Buffered transaction stream
  useEffect(() => {
    const es = new EventSource(`${API}/stream/transactions`)

    es.onmessage = e => {
      buffer.current.push(JSON.parse(e.data))
    }

    const interval = setInterval(() => {
      if (buffer.current.length > 0) {
        setTxns(prev => [...buffer.current, ...prev].slice(0, 300))
        buffer.current = []
      }
    }, 500)

    return () => {
      es.close()
      clearInterval(interval)
    }
  }, [])

  // Alert stream
  useEffect(() => {
    const es = new EventSource(`${API}/stream/alerts`)

    es.onmessage = e => {
      const alert = JSON.parse(e.data)
      setAlerts(prev => {
        const updated = [alert, ...prev]
        return updated
          .sort((a, b) => (b.ensemble_score || 0) - (a.ensemble_score || 0))
          .slice(0, 200)
      })
    }

    return () => es.close()
  }, [])

  // Metrics polling
  useEffect(() => {
    const fetchAll = async () => {
      try {
        setLoading(true)

        const [ana, sys, model] = await Promise.all([
          fetch(`${API}/metrics/analytics`).then(r => r.json()).catch(() => ({})),
          fetch(`${API}/metrics/system`).then(r => r.json()).catch(() => ({})),
          fetch(`${API}/metrics/model`).then(r => r.json()).catch(() => ({})),
        ])

        setAnalytics(ana)
        setSystemMetrics(sys)
        setModelMetrics(model)
        setError(null)

      } catch (err) {
        setError("Failed to load metrics")
      } finally {
        setLoading(false)
      }
    }

    fetchAll()
    const id = setInterval(fetchAll, 5000)
    return () => clearInterval(id)
  }, [])

  const loadExplanation = useCallback((txn) => {
    setSelected(txn)
    setExplanation("")

    if (esRef.current) esRef.current.close()

    const es = new EventSource(`${API}/stream/explain/${txn.txn_id}`)
    esRef.current = es

    es.onmessage = e => {
      const data = JSON.parse(e.data)
      if (data.done) { es.close(); return }
      if (data.token) {
        setExplanation(prev => prev + data.token)
        if (explainRef.current) {
          explainRef.current.scrollTop = explainRef.current.scrollHeight
        }
      }
    }
    es.onerror = () => es.close()
  }, [])

  const handleDecision = async (txnId, action) => {
    try {
      await fetch(`${API}/decision/${txnId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      })
      // Remove from alert queue
      setAlerts(prev => prev.filter(a => a.txn_id !== txnId))
    } catch (e) {
      console.error("Decision failed:", e)
    }
  }

  const trendData = (analytics?.trend || []).slice(-20)
  const histData = (analytics?.histogram || []).map(b => ({
    ...b,
    color: b.idx >= 8 ? "#ef4444" : b.idx >= 6 ? "#f97316" : b.idx >= 4 ? "#eab308" : "#22c55e"
  }))

  const latencyColor = (systemMetrics?.latency_ms || 0) < 200 ? "#22c55e" : (systemMetrics?.latency_ms || 0) < 500 ? "#f97316" : "#ef4444"

  return (
    <div style={{ height: "100%", overflow: "auto", display: "flex", flexDirection: "column", gap: 12 }}>

      {/* KPI BANNER */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        <KpiCard label="Throughput" value={`${systemMetrics?.tps || 0}`}
          sub="transactions/sec" color="#00E5FF" icon="⚡" />
        <KpiCard label="P99 Latency" value={`${systemMetrics?.latency_ms || 0}ms`}
          sub={`SLA: ${(systemMetrics?.latency_ms || 0) < 200 ? "✓ OK" : "✗ BREACH"}`} color={latencyColor} icon="⏱" />
        <KpiCard label="Fraud Alerts" value={systemMetrics?.alerts_per_min || 0}
          sub="alerts / minute" color="#f97316" icon="🚨" />
        <KpiCard label="Gateway Holds" value={systemMetrics?.held || 0}
          sub="transactions held" color="#eab308" icon="🔒" />
        <KpiCard label="False Positive Rate" value={`${systemMetrics?.fpr || 0}%`}
          sub={`Target ≤ 1.0% · Reviewed: ${modelMetrics?.total_reviewed || 0}`}
          color={(systemMetrics?.fpr || 0) <= 1 ? "#22c55e" : "#ef4444"} icon="📊" />
      </div>

      {/* MAIN 3-COLUMN LAYOUT */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px 380px", gap: 12, flex: 1, minHeight: 0 }}>

        {/* LEFT: Live Transaction Heatmap */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d", fontSize: 11, fontWeight: 700, color: "#a0aec0", display: "flex", justifyContent: "space-between" }}>
            <span>LIVE TRANSACTION FEED</span>
            <span style={{ fontSize: 10, color: "#4a5568" }}>{txns.length} in buffer</span>
          </div>
          <div style={{ flex: 1, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
              <thead>
                <tr style={{ position: "sticky", top: 0, background: "#0d1117", zIndex: 1 }}>
                  {["ID", "Amount", "Score", "Tier", "IF", "AE", "XGB", "Latency"].map(h => (
                    <th key={h} style={{ padding: "6px 8px", textAlign: "left", fontSize: 9, color: "#4a5568", borderBottom: "1px solid #30363d", textTransform: "uppercase", letterSpacing: "0.06em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {txns.slice(0, 200).map((txn, i) => {
                  const tc = tierOf(txn.risk_tier)
                  const latMs = txn.latency_ms || 0
                  const latColor = latMs < 200 ? "#22c55e" : latMs < 500 ? "#f97316" : "#ef4444"
                  return (
                    <tr key={txn.txn_id || i}
                      onClick={() => loadExplanation(txn)}
                      style={{
                        cursor: "pointer",
                        background: i === 0 ? tc.bg + "40" : "transparent",
                        borderBottom: "1px solid #1e2538",
                        animation: i === 0 ? "fadeIn 0.3s ease-out" : undefined,
                      }}>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", color: "#718096" }}>{txn.txn_id?.slice(0, 8)}</td>
                      <td style={{ padding: "5px 8px", color: "#e2e8f0" }}>₹{Number(txn.amount || 0).toLocaleString("en-IN")}</td>
                      <td style={{ padding: "5px 8px", color: tc.color, fontWeight: 700, fontFamily: "monospace" }}>{(txn.ensemble_score || 0).toFixed(3)}</td>
                      <td style={{ padding: "5px 8px" }}>
                        <span style={{ background: tc.bg, color: tc.color, border: `1px solid ${tc.border}`, borderRadius: 3, padding: "1px 5px", fontSize: 9, fontWeight: 700 }}>{tc.label}</span>
                      </td>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", color: "#a78bfa", fontSize: 10 }}>{(txn.if_score || 0).toFixed(3)}</td>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", color: "#38bdf8", fontSize: 10 }}>{(txn.ae_score || 0).toFixed(3)}</td>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", color: "#fb923c", fontSize: 10 }}>{(txn.xgb_score || 0).toFixed(3)}</td>
                      <td style={{ padding: "5px 8px", fontFamily: "monospace", color: latColor, fontSize: 10 }}>{latMs}ms</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* CENTER: Alert Queue */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d", fontSize: 11, fontWeight: 700, color: "#a0aec0", display: "flex", justifyContent: "space-between" }}>
            <span>🚨 ALERT QUEUE</span>
            <span style={{ fontSize: 10, color: "#ef4444", fontWeight: 700 }}>{alerts.length}</span>
          </div>
          <div style={{ flex: 1, overflow: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
            {alerts.length === 0 && (
              <div style={{ color: "#4a5568", fontSize: 12, textAlign: "center", padding: 40 }}>
                No alerts — all clear ✓
              </div>
            )}
            {alerts.slice(0, 50).map(alert => (
              <AlertCard
                key={alert.txn_id}
                alert={alert}
                isSelected={selected?.txn_id === alert.txn_id}
                onSelect={loadExplanation}
                onAction={handleDecision}
              />
            ))}
          </div>
        </div>

        {/* RIGHT: GenAI Explanation Panel */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d", fontSize: 11, fontWeight: 700, color: "#a0aec0" }}>
            AI FRAUD ANALYSIS
            {selected && <span style={{ marginLeft: 8, fontSize: 9, color: "#718096" }}>({selected.txn_id?.slice(0, 10)})</span>}
          </div>
          <div ref={explainRef} style={{ flex: 1, overflow: "auto", padding: 14, fontSize: 12, lineHeight: 1.8, color: "#cbd5e0", whiteSpace: "pre-wrap" }}>
            {!selected && <div style={{ color: "#4a5568", textAlign: "center", paddingTop: 60 }}>Select an alert to view AI explanation</div>}
            {selected && !explanation && <div style={{ color: "#718096", textAlign: "center", paddingTop: 60 }}>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "#22c55e", animation: "pulse 1s infinite", marginRight: 8 }} />
              Generating analysis…
            </div>}
            {explanation}
          </div>
        </div>
      </div>

      {/* BOTTOM: Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5568", textTransform: "uppercase", marginBottom: 8 }}>Fraud vs Legitimate Trend</div>
          <ResponsiveContainer width="100%" height={140}>
            <LineChart data={trendData}>
              <CartesianGrid stroke="#1e2538" />
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: "#4a5568" }} />
              <YAxis tick={{ fontSize: 9, fill: "#4a5568" }} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
              <Line dataKey="fraud" stroke="#ef4444" dot={false} strokeWidth={2} name="Fraud" />
              <Line dataKey="legit" stroke="#22c55e" dot={false} strokeWidth={2} name="Legit" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "12px 14px" }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#4a5568", textTransform: "uppercase", marginBottom: 8 }}>Ensemble Score Distribution</div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={histData}>
              <XAxis dataKey="range" tick={{ fontSize: 8, fill: "#4a5568" }} />
              <YAxis tick={{ fontSize: 9, fill: "#4a5568" }} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
              <Bar dataKey="count">
                {histData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

    </div>
  )
}
import { useState, useEffect, useRef } from "react"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine } from "recharts"

const API = "http://localhost:8000"

const TIER = {
  BLOCK:       { color: "#ef4444", bg: "#2d1515", border: "#ef4444" },
  HIGH:        { color: "#f97316", bg: "#2d1e0f", border: "#f97316" },
  SUSPICIOUS:  { color: "#eab308", bg: "#2d2a1a", border: "#eab308" },
  SAFE:        { color: "#22c55e", bg: "#1c3829", border: "#22c55e" },
  Block:       { color: "#ef4444", bg: "#2d1515", border: "#ef4444" },
  "High-Risk": { color: "#f97316", bg: "#2d1e0f", border: "#f97316" },
  Suspicious:  { color: "#eab308", bg: "#2d2a1a", border: "#eab308" },
  Legitimate:  { color: "#22c55e", bg: "#1c3829", border: "#22c55e" },
}
const tierOf = t => TIER[t] || { color: "#718096", bg: "#1a1d2e", border: "#2d3748" }

const ALL_FEATURES = [
  // Velocity
  "txn_count_1min","txn_count_5min","txn_count_1hr",
  "amount_sum_1hr","unique_receivers_1hr","unique_devices_1hr",
  // Amount
  "amount","amount_zscore","amount_vs_daily_avg","is_round_number",
  // Temporal
  "hour_of_day","day_of_week","is_weekend","is_night","days_since_last_txn",
  // Device
  "is_new_device","device_txn_count","device_vpa_count","device_risk_score",
  // Geo
  "distance_from_last_txn_km","txn_speed_kmph","is_geo_impossible",
  // Graph
  "sender_degree_1hr","receiver_degree_1hr","chain_length","sender_pagerank","receiver_pagerank",
  "fraud_hop_count","is_star_receiver",
  // Merchant
  "merchant_category_risk","merchant_dispute_rate","is_mule_account",
  // VPA
  "vpa_similarity_score",
]

const FEATURE_GROUPS = {
  "Velocity":  ["txn_count_1min","txn_count_5min","txn_count_1hr","amount_sum_1hr","unique_receivers_1hr","unique_devices_1hr"],
  "Amount":    ["amount","amount_zscore","amount_vs_daily_avg","is_round_number"],
  "Temporal":  ["hour_of_day","day_of_week","is_weekend","is_night","days_since_last_txn"],
  "Device":    ["is_new_device","device_txn_count","device_vpa_count","device_risk_score"],
  "Graph":     ["sender_degree_1hr","receiver_degree_1hr","chain_length","sender_pagerank","receiver_pagerank","fraud_hop_count","is_star_receiver"],
  "Risk Flags":["merchant_category_risk","merchant_dispute_rate","is_mule_account","is_geo_impossible","vpa_similarity_score"],
}

function TierBadge({ tier }) {
  const t = tierOf(tier)
  return (
    <span style={{ background: t.bg, color: t.color, border: `1px solid ${t.border}`, borderRadius: 4, padding: "2px 8px", fontSize: 10, fontWeight: 700, letterSpacing: "0.05em" }}>
      {tier}
    </span>
  )
}

function FeatureCell({ label, value }) {
  const isRisk = typeof value === "number" && value > 0.7 && ["risk","score","zscore","count","speed"].some(k => label.includes(k))
  const isBool = value === true || value === 1 || value === "1"
  const color  = isBool ? "#ef4444" : isRisk ? "#f97316" : "#e2e8f0"
  return (
    <div style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 6, padding: "7px 10px" }}>
      <div style={{ fontSize: 9, color: "#4a5568", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 12, fontWeight: 600, color }}>{value !== undefined && value !== null ? String(value) : "—"}</div>
    </div>
  )
}

// SHAP Waterfall Chart
function ShapWaterfall({ shap_top5, base_value = 0.5, ensemble_score }) {
  if (!shap_top5 || shap_top5.length === 0) return (
    <div style={{ color: "#4a5568", fontSize: 12, textAlign: "center", padding: 24 }}>No SHAP data available</div>
  )

  // Build waterfall: starting from base_value, each feature adds/subtracts
  let running = base_value
  const bars = shap_top5.map((s, i) => {
    const contribution = s.shap || (s.direction === "increases_risk" ? Math.abs(s.value || 0.05) : -Math.abs(s.value || 0.05))
    const start = running
    running += contribution
    return {
      feature: s.feature,
      shap: contribution,
      start,
      end: running,
      color: contribution > 0 ? "#ef4444" : "#22c55e",
      label: `${contribution > 0 ? "+" : ""}${contribution.toFixed(3)}`,
    }
  })

  // Add base and final bars
  const chartData = [
    { name: "Base", value: base_value, start: 0, shap: base_value, color: "#63b3ed", label: base_value.toFixed(3) },
    ...bars.map(b => ({ name: b.feature.replace(/_/g, " ").slice(0, 18), value: Math.abs(b.shap), start: Math.min(b.start, b.end), shap: b.shap, color: b.color, label: b.label })),
    { name: "Final", value: ensemble_score || running, start: 0, shap: ensemble_score || running, color: tierOf(null).color, label: (ensemble_score || running).toFixed(3) },
  ]

  return (
    <div>
      <div style={{ fontSize: 11, color: "#718096", marginBottom: 10 }}>
        Base value: <span style={{ color: "#63b3ed", fontWeight: 700 }}>{base_value.toFixed(3)}</span>
        {"  →  "}
        Final score: <span style={{ color: "#e2e8f0", fontWeight: 700 }}>{(ensemble_score || running).toFixed(3)}</span>
      </div>
      {shap_top5.map((s, i) => {
        const contribution = s.shap || (s.direction === "increases_risk" ? 0.05 : -0.05)
        const isPos = contribution > 0 || s.direction === "increases_risk"
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <div style={{ fontSize: 10, color: "#a0aec0", width: 160, flexShrink: 0 }}>{s.feature?.replace(/_/g, " ")}</div>
            <div style={{ flex: 1, height: 18, background: "#0d1117", borderRadius: 3, position: "relative", overflow: "hidden" }}>
              <div style={{
                position: "absolute", height: "100%",
                width: `${Math.min(100, Math.abs(contribution) * 200)}%`,
                left: isPos ? "50%" : undefined,
                right: isPos ? undefined : "50%",
                background: isPos ? "#ef4444" : "#22c55e",
                borderRadius: 3, opacity: 0.8,
              }} />
              <div style={{ position: "absolute", left: "50%", top: 0, width: 1, height: "100%", background: "#30363d" }} />
            </div>
            <div style={{ fontSize: 11, fontWeight: 700, color: isPos ? "#ef4444" : "#22c55e", width: 55, textAlign: "right", fontFamily: "monospace" }}>
              {isPos ? "+" : ""}{s.shap?.toFixed(4) ?? (isPos ? "+0.05" : "-0.05")}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// VPA Timeline
function VpaTimeline({ txns, currentId }) {
  if (!txns || txns.length === 0) return <div style={{ color: "#4a5568", fontSize: 12 }}>No timeline data</div>

  return (
    <div style={{ maxHeight: 260, overflow: "auto" }}>
      {txns.map((t, i) => {
        const tc = tierOf(t.risk_tier)
        const isCurrentTxn = t.txn_id === currentId
        return (
          <div key={t.txn_id || i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "7px 10px",
            background: isCurrentTxn ? tc.bg : "transparent",
            border: isCurrentTxn ? `1px solid ${tc.border}` : "1px solid transparent",
            borderRadius: 6, marginBottom: 4,
          }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: tc.color, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 10, color: "#718096", fontFamily: "monospace" }}>
                {t.txn_id?.slice(0, 10)}
                {isCurrentTxn && <span style={{ color: tc.color, marginLeft: 6 }}>[SELECTED]</span>}
              </div>
              <div style={{ fontSize: 11, color: "#e2e8f0", fontWeight: 600 }}>₹{Number(t.amount || 0).toLocaleString("en-IN")}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <TierBadge tier={t.risk_tier} />
              <div style={{ fontSize: 9, color: "#4a5568", marginTop: 2 }}>score: {(t.ensemble_score || 0).toFixed(3)}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default function TransactionInvestigator() {
  const [query, setQuery]         = useState("")
  const [searchType, setSearchType] = useState("txn_id")
  const [result, setResult]       = useState(null)
  const [timeline, setTimeline]   = useState([])
  const [loading, setLoading]     = useState(false)
  const [note, setNote]           = useState("")
  const [noteSaved, setNoteSaved] = useState(false)
  const [activeTab, setActiveTab] = useState("overview")
  const [bufferCount, setBufferCount] = useState(0)
  const [explanation, setExplanation] = useState("")
  const [streaming, setStreaming] = useState(false)
  const explainRef = useRef(null)

  // Fetch buffer size for hint text only
  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => r.json())
      .then(h => setBufferCount(h?.txns || 0))
      .catch(() => {})
  }, [])

  const search = async () => {
    if (!query.trim()) return
    setLoading(true)
    setResult(null)
    setTimeline([])
    setExplanation("")

    try {
      if (searchType === "txn_id") {
        const res  = await fetch(`${API}/transaction/${encodeURIComponent(query.trim())}`)
        const data = await res.json()
        if (!data.error) {
          setResult(data)
          if (data.sender_vpa) {
            const tlRes = await fetch(`${API}/investigate/timeline/${encodeURIComponent(data.sender_vpa)}?limit=30`)
            const tlData = await tlRes.json()
            setTimeline(tlData.timeline || [])
          }
        }
      } else {
        const amount = Number.parseFloat(query.trim())
        const params = new URLSearchParams({
          search_type: searchType,
          query: searchType === "amount" ? "" : query.trim(),
          limit: "50",
        })
        if (searchType === "amount" && Number.isFinite(amount)) {
          const spread = Math.max(100, amount * 0.05)
          params.set("min_amount", String(Math.max(0, amount - spread)))
          params.set("max_amount", String(amount + spread))
        }
        const res = await fetch(`${API}/investigate/search?${params.toString()}`)
        const payload = await res.json()
        const matches = payload.results || []
        if (matches.length > 0) {
          setResult(matches[0])
          setTimeline(matches)
        }
      }
    } catch (e) {
      console.error(e)
    }
    setLoading(false)
  }

  const loadExplanation = () => {
    if (!result) return
    setExplanation("")
    setStreaming(true)
    const es = new EventSource(`${API}/stream/explain/${result.txn_id}`)
    es.onmessage = e => {
      const data = JSON.parse(e.data)
      if (data.done) { setStreaming(false); es.close(); return }
      if (data.token) {
        setExplanation(prev => prev + data.token)
        if (explainRef.current) explainRef.current.scrollTop = explainRef.current.scrollHeight
      }
    }
    es.onerror = () => { setStreaming(false); es.close() }
  }

  const saveNote = async () => {
    if (!result || !note.trim()) return
    await fetch(`${API}/decision/${result.txn_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "Note", note }),
    })
    setNoteSaved(true)
    setTimeout(() => setNoteSaved(false), 3000)
  }

  const tc = result ? tierOf(result.risk_tier) : null

  const TABS = [
    { id: "overview", label: "Overview" },
    { id: "features", label: "All Features" },
    { id: "shap",     label: "SHAP Waterfall" },
    { id: "timeline", label: `Timeline (${timeline.length})` },
    { id: "explain",  label: "AI Explanation" },
  ]

  return (
    <div style={{ height: "100%", overflow: "auto", display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ── Search Bar ─────────────────────────────────────────────────────── */}
      <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Transaction Investigator
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {/* Search type selector */}
          <div style={{ display: "flex", background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, overflow: "hidden" }}>
            {[
              { id: "txn_id", label: "Txn ID" },
              { id: "vpa",    label: "VPA" },
              { id: "device", label: "Device" },
              { id: "amount", label: "Amount" },
            ].map(t => (
              <button key={t.id} onClick={() => setSearchType(t.id)}
                style={{
                  padding: "8px 14px", border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600,
                  background: searchType === t.id ? "#1f2937" : "transparent",
                  color: searchType === t.id ? "#00E5FF" : "#718096",
                  borderRight: "1px solid #30363d",
                }}>
                {t.label}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && search()}
            placeholder={
              searchType === "txn_id" ? "Enter transaction ID..." :
              searchType === "vpa" ? "Enter VPA (e.g. user@oksbi)..." :
              searchType === "device" ? "Enter device ID..." :
              "Enter amount (₹)..."
            }
            style={{
              flex: 1, minWidth: 200, background: "#0d1117", border: "1px solid #30363d",
              borderRadius: 8, padding: "8px 14px", color: "#e2e8f0", fontSize: 13, outline: "none",
            }}
          />
          <button onClick={search} style={{
            padding: "8px 24px", background: "#1d4ed8", border: "none",
            borderRadius: 8, color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>
            {loading ? "Searching…" : "🔍 Search"}
          </button>
        </div>
        {!result && !loading && (
          <div style={{ marginTop: 10, fontSize: 11, color: "#4a5568" }}>
            Search from live gateway stream and alert buffer · cached rows: {bufferCount.toLocaleString()}
          </div>
        )}
      </div>

      {/* ── Results ────────────────────────────────────────────────────────── */}
      {result && (
        <div style={{ background: "#161B22", border: `1px solid ${tc?.border || "#30363d"}`, borderRadius: 10, overflow: "hidden", flex: 1 }}>

          {/* Result Header */}
          <div style={{ padding: "12px 16px", borderBottom: "1px solid #30363d", background: tc?.bg + "55", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <TierBadge tier={result.risk_tier} />
              <span style={{ fontFamily: "monospace", fontSize: 11, color: "#718096" }}>{result.txn_id}</span>
              {result.fraud_flag && <span style={{ fontSize: 10, color: "#f97316", background: "#2d1e0f", border: "1px solid #f97316", borderRadius: 4, padding: "1px 6px" }}>{result.fraud_flag}</span>}
            </div>
            <div style={{ display: "flex", gap: 20 }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 10, color: "#4a5568" }}>Amount</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "#e2e8f0" }}>₹{Number(result.amount || 0).toLocaleString("en-IN")}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 10, color: "#4a5568" }}>Ensemble Score</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: tc?.color }}>{(result.ensemble_score || 0).toFixed(4)}</div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 10, color: "#4a5568" }}>Confidence</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: result.confidence === "HIGH" ? "#22c55e" : result.confidence === "MEDIUM" ? "#eab308" : "#718096" }}>
                  {result.confidence || "—"}
                </div>
              </div>
            </div>
          </div>

          {/* Quick Model Scores */}
          <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #30363d" }}>
            {[
              { label: "Isolation Forest", value: result.if_score,       color: "#a78bfa" },
              { label: "Autoencoder Error", value: result.ae_score,      color: "#38bdf8" },
              { label: "XGBoost Prob",      value: result.xgb_score,     color: "#fb923c" },
              { label: "Latency",           value: result.total_latency_ms, unit: "ms", color: result.total_latency_ms < 200 ? "#22c55e" : "#ef4444" },
            ].map((m, i) => (
              <div key={m.label} style={{ flex: 1, padding: "10px 14px", borderRight: i < 3 ? "1px solid #30363d" : "none" }}>
                <div style={{ fontSize: 9, color: "#4a5568", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{m.label}</div>
                <div style={{ fontSize: 16, fontWeight: 800, color: m.color }}>
                  {m.value != null ? (m.unit ? `${m.value}${m.unit}` : m.value.toFixed(4)) : "—"}
                </div>
              </div>
            ))}
          </div>

          {/* VPA Row */}
          <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #30363d" }}>
            {[
              { label: "Sender VPA",   value: result.sender_vpa   || "—" },
              { label: "Receiver VPA", value: result.receiver_vpa || "—" },
              { label: "Device ID",    value: result.device_id    || "—" },
              { label: "Fraud Pattern", value: result.fraud_flag  || "—", color: "#f97316" },
            ].map((f, i) => (
              <div key={f.label} style={{ flex: 1, padding: "10px 14px", borderRight: i < 3 ? "1px solid #30363d" : "none" }}>
                <div style={{ fontSize: 9, color: "#4a5568", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{f.label}</div>
                <div style={{ fontSize: 11, color: f.color || "#e2e8f0", fontFamily: "monospace", wordBreak: "break-all" }}>{f.value}</div>
              </div>
            ))}
          </div>

          {/* Tab Bar */}
          <div style={{ display: "flex", borderBottom: "1px solid #30363d", background: "#0d1117" }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => { setActiveTab(t.id); if (t.id === "explain" && !explanation) loadExplanation() }}
                style={{
                  padding: "10px 16px", border: "none", cursor: "pointer", fontSize: 11, fontWeight: 600,
                  background: "transparent", color: activeTab === t.id ? "#00E5FF" : "#718096",
                  borderBottom: activeTab === t.id ? "2px solid #00E5FF" : "2px solid transparent",
                }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div style={{ padding: 16, overflow: "auto", maxHeight: "calc(100vh - 480px)" }}>

            {/* Overview Tab */}
            {activeTab === "overview" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                {/* Top SHAP features quick view */}
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 10 }}>Top SHAP Features</div>
                  {result.shap_top5 ? result.shap_top5.map((s, i) => {
                    const isPos = s.direction === "increases_risk" || (s.shap || 0) > 0
                    return (
                      <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #1e2538" }}>
                        <span style={{ fontSize: 11, color: "#a0aec0" }}>{s.feature?.replace(/_/g, " ")}</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: isPos ? "#ef4444" : "#22c55e", fontFamily: "monospace" }}>
                          {isPos ? "↑" : "↓"} {s.shap != null ? (isPos ? "+" : "") + s.shap.toFixed(4) : s.value?.toFixed(4) || "—"}
                        </span>
                      </div>
                    )
                  }) : <div style={{ color: "#4a5568", fontSize: 12 }}>No SHAP data</div>}
                </div>

                {/* Reasons / Risk signals */}
                <div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 10 }}>Risk Signals</div>
                  {result.reasons && result.reasons.length > 0 ? result.reasons.map((r, i) => (
                    <div key={i} style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 6, padding: "8px 10px", marginBottom: 6 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                        <span style={{ fontSize: 10, color: "#718096", textTransform: "uppercase" }}>{r.type?.replace(/_/g, " ")}</span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: r.impact === "critical" ? "#ef4444" : r.impact === "high" ? "#f97316" : "#eab308" }}>
                          {r.impact?.toUpperCase()}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: "#e2e8f0" }}>{r.desc}</div>
                    </div>
                  )) : <div style={{ color: "#4a5568", fontSize: 12 }}>No risk signals detected</div>}

                  {/* Analyst note */}
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 8 }}>Investigation Notes</div>
                    <textarea value={note} onChange={e => setNote(e.target.value)}
                      placeholder="Document investigation findings..."
                      style={{ width: "100%", minHeight: 70, background: "#0d1117", border: "1px solid #30363d", borderRadius: 6, padding: 10, color: "#e2e8f0", fontSize: 12, resize: "vertical", outline: "none", boxSizing: "border-box" }} />
                    <button onClick={saveNote} style={{
                      marginTop: 6, padding: "6px 16px", background: noteSaved ? "#14532d" : "transparent",
                      border: `1px solid ${noteSaved ? "#22c55e" : "#1d4ed8"}`, borderRadius: 6,
                      color: noteSaved ? "#22c55e" : "#63b3ed", fontSize: 11, cursor: "pointer", fontWeight: 600,
                    }}>
                      {noteSaved ? "✓ Saved" : "Save Note"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* All Features Tab */}
            {activeTab === "features" && (
              <div>
                {Object.entries(FEATURE_GROUPS).map(([group, cols]) => (
                  <div key={group} style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#718096", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 8, borderBottom: "1px solid #30363d", paddingBottom: 4 }}>
                      {group}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 6 }}>
                      {cols.map(col => (
                        <FeatureCell key={col} label={col} value={result[col]} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* SHAP Waterfall Tab */}
            {activeTab === "shap" && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 14 }}>
                  SHAP Waterfall — Feature Contributions to Ensemble Score
                </div>
                <ShapWaterfall shap_top5={result.shap_top5} base_value={0.5} ensemble_score={result.ensemble_score} />
                <div style={{ marginTop: 20, padding: "10px 14px", background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, fontSize: 11, color: "#718096" }}>
                  <strong style={{ color: "#a0aec0" }}>Reading guide:</strong> Red bars push the score higher (toward fraud). Green bars push it lower (toward legitimate). The sum of all bars + base value = final ensemble score.
                </div>
              </div>
            )}

            {/* Timeline Tab */}
            {activeTab === "timeline" && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0", marginBottom: 10 }}>
                  VPA Transaction History — {result.sender_vpa || "Unknown"}
                </div>
                <VpaTimeline txns={timeline} currentId={result.txn_id} />
                {timeline.length === 0 && (
                  <div style={{ color: "#4a5568", fontSize: 12, textAlign: "center", padding: 24 }}>
                    No timeline data — transaction may not be in the current in-memory window.
                  </div>
                )}
              </div>
            )}

            {/* AI Explanation Tab */}
            {activeTab === "explain" && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#a0aec0" }}>
                    AI Fraud Analysis
                    {streaming && <span style={{ marginLeft: 8, width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block", animation: "pulse 1s infinite" }} />}
                  </div>
                  {!streaming && explanation && (
                    <button onClick={loadExplanation} style={{ fontSize: 10, color: "#63b3ed", background: "transparent", border: "1px solid #1d4ed8", borderRadius: 4, padding: "4px 10px", cursor: "pointer" }}>
                      Regenerate
                    </button>
                  )}
                </div>
                <div ref={explainRef} style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, padding: 14, minHeight: 200, maxHeight: 400, overflow: "auto", fontSize: 12, lineHeight: 1.75, color: "#cbd5e0", whiteSpace: "pre-wrap" }}>
                  {!explanation && !streaming && <div style={{ color: "#4a5568", textAlign: "center", paddingTop: 60 }}>Loading AI analysis…</div>}
                  {!explanation && streaming && <div style={{ color: "#718096" }}>Generating analysis…</div>}
                  {explanation}
                </div>
              </div>
            )}

          </div>
        </div>
      )}

      {!result && !loading && (
        <div style={{ flex: 1, background: "#161B22", border: "1px solid #30363d", borderRadius: 10, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#4a5568", gap: 12 }}>
          <div style={{ fontSize: 40 }}>🔍</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#718096" }}>Search for a transaction to investigate</div>
          <div style={{ fontSize: 12 }}>Search by Transaction ID, VPA, Device ID, or Amount</div>
          <div style={{ fontSize: 11, color: "#2d3748", marginTop: 8 }}>{bufferCount.toLocaleString()} transactions in current gateway cache</div>
        </div>
      )}

      {loading && (
        <div style={{ flex: 1, background: "#161B22", border: "1px solid #30363d", borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", color: "#718096", fontSize: 13 }}>
          Searching…
        </div>
      )}
    </div>
  )
}
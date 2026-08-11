import { useState, useEffect } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
         RadarChart, Radar, PolarGrid, PolarAngleAxis,
         BarChart, Bar, Cell, ReferenceLine } from "recharts"

const API = "http://localhost:8000"

function MetricTile({ label, value, sub, color }) {
  return (
    <div style={{ background: "#0d1117", borderRadius: 8, padding: "12px 14px", border: "1px solid #30363d" }}>
      <div style={{ fontSize: 9, color: "#4a5568", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: "#718096", marginTop: 3 }}>{sub}</div>}
    </div>
  )
}

// Global SHAP Summary — top features driving fraud detections
function ShapSummaryChart({ txns }) {
  // Aggregate SHAP values across all transactions
  const featureMap = {}
  let count = 0
  txns.forEach(t => {
    if (!t.shap_top5) return
    count++
    t.shap_top5.forEach(s => {
      const key = s.feature
      if (!featureMap[key]) featureMap[key] = { pos: 0, neg: 0, total: 0 }
      const contribution = s.shap || (s.direction === "increases_risk" ? 0.05 : -0.05)
      if (contribution > 0) featureMap[key].pos += contribution
      else featureMap[key].neg += Math.abs(contribution)
      featureMap[key].total += Math.abs(contribution)
    })
  })

  const chartData = Object.entries(featureMap)
    .sort((a, b) => b[1].total - a[1].total)
    .slice(0, 12)
    .map(([feature, d]) => ({
      feature: feature.replace(/_/g, " ").slice(0, 20),
      positive: +(d.pos / Math.max(count, 1)).toFixed(4),
      negative: -(d.neg / Math.max(count, 1)).toFixed(4),
    }))

  if (chartData.length === 0) return (
    <div style={{ color: "#4a5568", fontSize: 12, textAlign: "center", padding: 40 }}>
      No SHAP data yet — waiting for analyst-reviewed transactions
    </div>
  )

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
        <XAxis type="number" tick={{ fontSize: 9, fill: "#4a5568" }}
          tickFormatter={v => v.toFixed(3)} />
        <YAxis type="category" dataKey="feature" tick={{ fontSize: 9, fill: "#a0aec0" }} width={130} />
        <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }}
          formatter={(v, name) => [Math.abs(v).toFixed(4), name === "positive" ? "↑ Increases Risk" : "↓ Reduces Risk"]} />
        <ReferenceLine x={0} stroke="#30363d" />
        <Bar dataKey="positive" fill="#ef4444" stackId="a" radius={[0,3,3,0]} />
        <Bar dataKey="negative" fill="#22c55e" stackId="b" radius={[3,0,0,3]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function ModelPerformance() {
  const [metrics, setMetrics]     = useState(null)
  const [sysMetrics, setSysMetrics] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [recentTxns, setRecentTxns] = useState([])
  const [threshold, setThreshold] = useState(0.90)
  const [history, setHistory]     = useState([])

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [m, s, a, txns] = await Promise.all([
          fetch(`${API}/metrics/model`).then(r => r.json()),
          fetch(`${API}/metrics/system`).then(r => r.json()),
          fetch(`${API}/metrics/analytics`).then(r => r.json()),
          fetch(`${API}/transactions?limit=1000`).then(r => r.json()),
        ])
        setMetrics(m)
        setSysMetrics(s)
        setAnalytics(a)
        setRecentTxns(Array.isArray(txns) ? txns : [])
        setHistory(prev => [...prev, {
          t: new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          fpr:    s.fpr    ?? 0,
          recall: s.recall ?? 0,
        }].slice(-30))
      } catch (_) {}
    }
    fetchAll()
    const id = setInterval(fetchAll, 8000)
    return () => clearInterval(id)
  }, [])

  const tp    = metrics?.true_positives    || 0
  const fp    = metrics?.false_positives   || 0
  const fn    = metrics?.false_negatives   || 0
  const tn    = metrics?.true_negatives    || 0
  const total = metrics?.total_reviewed    || 0

  const precision = metrics?.precision ?? (tp + fp > 0 ? Math.round(tp / (tp + fp) * 100) : 0)
  const recall    = metrics?.recall ?? (sysMetrics?.recall ?? 0)
  const fpr       = metrics?.false_positive_rate ?? (sysMetrics?.fpr ?? 0)

  const radarData = [
    { subject: "Recall",    A: recall },
    { subject: "Precision", A: precision },
    { subject: "FPR↓",     A: Math.max(0, 100 - fpr) },
    { subject: "Coverage",  A: Math.min(100, total) },
    { subject: "SLA",       A: sysMetrics?.sla_ok ? 100 : 50 },
  ]

  const ms = analytics?.model_scores || {}
  const modelBarData = [
    { name: "IF Score",  value: ms.iso_avg      ?? 0, color: "#a78bfa" },
    { name: "AE Error",  value: ms.ae_avg       ?? 0, color: "#38bdf8" },
    { name: "XGB Prob",  value: ms.xgb_avg      ?? 0, color: "#fb923c" },
    { name: "Ensemble",  value: ms.ensemble_avg ?? 0, color: "#f87171" },
  ]

  const withLabels = recentTxns.filter(t => t.is_fraud === 0 || t.is_fraud === 1)
  const calcPRPoint = (scoreKey, thresh) => {
    const pred = withLabels.map(t => Number(t[scoreKey] || 0) >= thresh ? 1 : 0)
    let pTP = 0, pFP = 0, pFN = 0
    withLabels.forEach((t, i) => {
      const actual = Number(t.is_fraud)
      if (pred[i] === 1 && actual === 1) pTP += 1
      else if (pred[i] === 1 && actual === 0) pFP += 1
      else if (pred[i] === 0 && actual === 1) pFN += 1
    })
    const pr = pTP + pFP > 0 ? pTP / (pTP + pFP) : 0
    const rc = pTP + pFN > 0 ? pTP / (pTP + pFN) : 0
    return { pr, rc }
  }
  const prCurve = Array.from({ length: 11 }, (_, i) => i / 10).map(thresh => {
    const e = calcPRPoint("ensemble_score", thresh)
    const x = calcPRPoint("xgb_score", thresh)
    const f = calcPRPoint("if_score", thresh)
    return {
      recall: e.rc,
      precision_ensemble: e.pr,
      precision_xgb: x.pr,
      precision_if: f.pr,
    }
  }).sort((a, b) => a.recall - b.recall)

  const blockPred = withLabels.map(t => Number(t.ensemble_score || 0) >= threshold ? 1 : 0)
  let bTP = 0, bFP = 0, bFN = 0, bTN = 0
  withLabels.forEach((t, i) => {
    const actual = Number(t.is_fraud)
    const pred = blockPred[i]
    if (pred === 1 && actual === 1) bTP += 1
    else if (pred === 1 && actual === 0) bFP += 1
    else if (pred === 0 && actual === 1) bFN += 1
    else bTN += 1
  })
  const computedRecall = (bTP + bFN > 0 ? (bTP / (bTP + bFN)) * 100 : 0).toFixed(1)
  const computedFPR = (bFP + bTN > 0 ? (bFP / (bFP + bTN)) * 100 : 0).toFixed(2)
  const computedBlockRate = (withLabels.length > 0 ? (blockPred.reduce((a, b) => a + b, 0) / withLabels.length) * 100 : 0).toFixed(1)

  return (
    <div style={{ height: "100%", overflow: "auto", display: "flex", flexDirection: "column", gap: 14 }}>

      {/* ── Row 1: Confusion Matrix + Sub-model Scores + Radar ─────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>

        {/* Confusion Matrix */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Confusion Matrix (Analyst Reviewed)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
            {[
              { label: "True Positives",   value: tp, color: "#22c55e", desc: "Fraud correctly caught" },
              { label: "False Positives",  value: fp, color: "#ef4444", desc: "Legit wrongly flagged" },
              { label: "True Negatives",   value: tn, color: "#22c55e", desc: "Legit correctly passed" },
              { label: "False Negatives",  value: fn, color: "#f97316", desc: "Fraud missed (est.)" },
            ].map(c => (
              <div key={c.label} style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, padding: 10 }}>
                <div style={{ fontSize: 9, color: "#4a5568", textTransform: "uppercase", marginBottom: 3 }}>{c.label}</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: c.color }}>{c.value}</div>
                <div style={{ fontSize: 9, color: "#718096" }}>{c.desc}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <MetricTile label="Fraud Catch Rate" value={`${metrics?.fraud_catch_rate || 0}%`}
              sub="Target ≥ 85%"
              color={metrics?.fraud_catch_rate >= 85 ? "#22c55e" : "#ef4444"} />
            {/* PDF says FPR target is ≤ 1.0% */}
            <MetricTile label="False Positive Rate" value={`${metrics?.false_positive_rate || 0}%`}
              sub="Target ≤ 1.0%"
              color={metrics?.false_positive_rate <= 1 ? "#22c55e" : "#ef4444"} />
          </div>
          <div style={{ marginTop: 8, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <MetricTile label="Precision" value={`${precision}%`} sub="Target ≥ 40%" color={precision >= 40 ? "#22c55e" : "#ef4444"} />
            <MetricTile label="Total Reviewed" value={total} sub="analyst decisions" color="#63b3ed" />
          </div>
        </div>

        {/* Sub-model Score Breakdown */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Sub-Model Avg Scores (Last 1000 Txns)
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={modelBarData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
              <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 9, fill: "#4a5568" }} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 10, fill: "#a0aec0" }} width={80} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} formatter={v => v.toFixed(4)} />
              <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                {modelBarData.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 8 }}>Ensemble Weights (per spec)</div>
            {[
              { label: "Isolation Forest",  weight: "25%", color: "#a78bfa" },
              { label: "Autoencoder",       weight: "25%", color: "#38bdf8" },
              { label: "XGBoost",           weight: "50%", color: "#fb923c" },
            ].map(w => (
              <div key={w.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "4px 0", borderBottom: "1px solid #1e2538" }}>
                <span style={{ color: w.color }}>● {w.label}</span>
                <span style={{ color: "#e2e8f0", fontWeight: 700 }}>{w.weight}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, fontSize: 10, color: "#4a5568" }}>
            ensemble = 0.25×IF + 0.25×AE + 0.50×XGB + rule_boost (max 0.20)
          </div>
        </div>

        {/* Radar Performance Profile */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Model Performance Profile
          </div>
          <ResponsiveContainer width="100%" height={190}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#2d3748" />
              <PolarAngleAxis dataKey="subject" tick={{ fontSize: 10, fill: "#a0aec0" }} />
              <Radar dataKey="A" stroke="#00E5FF" fill="#00E5FF" fillOpacity={0.15} strokeWidth={2} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
            </RadarChart>
          </ResponsiveContainer>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginTop: 4 }}>
            <MetricTile label="Live F2-Score" value={metrics?.f2_score ?? 0} color="#00E5FF" sub="from analyst decisions" />
            <MetricTile label="Labeled Samples" value={withLabels.length} color="#00E5FF" sub="for PR/FPR/threshold curves" />
          </div>
        </div>
      </div>

      {/* ── Row 2: PR Curve + FPR/Recall History ───────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>

        {/* Precision-Recall Curve */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Precision-Recall Curve (Live from labeled stream)
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={prCurve}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
              <XAxis dataKey="recall" type="number" domain={[0,1]} tick={{ fontSize: 9, fill: "#4a5568" }} label={{ value: "Recall", position: "insideBottomRight", fill: "#4a5568", fontSize: 9 }} />
              <YAxis domain={[0,1]} tick={{ fontSize: 9, fill: "#4a5568" }} label={{ value: "Precision", angle: -90, position: "insideLeft", fill: "#4a5568", fontSize: 9 }} />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} formatter={v => v.toFixed(3)} />
              <ReferenceLine y={0.40} stroke="#718096" strokeDasharray="4 2" label={{ value: "≥40% target", fill: "#718096", fontSize: 9 }} />
              <Line type="monotone" dataKey="precision_ensemble" stroke="#22c55e" dot={false} strokeWidth={2.5} name="Ensemble" />
              <Line type="monotone" dataKey="precision_xgb"      stroke="#fb923c" dot={false} strokeWidth={1.5} name="XGBoost" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="precision_if"       stroke="#a78bfa" dot={false} strokeWidth={1.5} name="IF"      strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 14, marginTop: 6, fontSize: 10 }}>
            <span style={{ color: "#22c55e" }}>● Ensemble</span>
            <span style={{ color: "#fb923c" }}>● XGBoost</span>
            <span style={{ color: "#a78bfa" }}>● Isolation Forest</span>
          </div>
        </div>

        {/* Live FPR / Recall history */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Live FPR vs Recall (Analyst Feedback Loop)
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2538" />
              <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#4a5568" }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#4a5568" }} unit="%" />
              <Tooltip contentStyle={{ background: "#161B22", border: "1px solid #30363d", fontSize: 11 }} />
              <ReferenceLine y={85} stroke="#22c55e" strokeDasharray="4 2" label={{ value: "85% recall target", fill: "#22c55e", fontSize: 9 }} />
              <ReferenceLine y={1}  stroke="#ef4444" strokeDasharray="4 2" label={{ value: "1% FPR limit", fill: "#ef4444", fontSize: 9 }} />
              <Line type="monotone" dataKey="fpr"    stroke="#ef4444" dot={false} strokeWidth={2} name="FPR" />
              <Line type="monotone" dataKey="recall" stroke="#22c55e" dot={false} strokeWidth={2} name="Recall" />
            </LineChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 10 }}>
            <span style={{ color: "#ef4444" }}>● FPR (target ≤1%)</span>
            <span style={{ color: "#22c55e" }}>● Recall (target ≥85%)</span>
          </div>
        </div>
      </div>

      {/* ── Row 3: Global SHAP Summary + Threshold Tuner + Drift ───────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>

        {/* Global SHAP Summary */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Global SHAP Feature Importance
          </div>
          <div style={{ fontSize: 10, color: "#4a5568", marginBottom: 8 }}>Avg contribution across last {recentTxns.length} transactions</div>
          <ShapSummaryChart txns={recentTxns} />
          <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 10 }}>
            <span style={{ color: "#ef4444" }}>■ Increases risk</span>
            <span style={{ color: "#22c55e" }}>■ Reduces risk</span>
          </div>
        </div>

        {/* Threshold Tuner */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 14, textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Threshold Tuner
          </div>
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 11 }}>
              <span style={{ color: "#718096" }}>BLOCK threshold</span>
              <span style={{ color: "#ef4444", fontWeight: 800 }}>{threshold.toFixed(2)}</span>
            </div>
            <input type="range" min="0.60" max="0.99" step="0.01"
              value={threshold} onChange={e => setThreshold(parseFloat(e.target.value))}
              style={{ width: "100%", accentColor: "#ef4444" }} />
          </div>

          {/* Real-time impact preview (<300ms, client-side calc) */}
          <div style={{ background: "#0d1117", border: "1px solid #30363d", borderRadius: 8, padding: "10px 12px", marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: "#718096", marginBottom: 8, textTransform: "uppercase" }}>Impact Preview (Real-time)</div>
            {[
              { label: "Computed Recall",         value: `${computedRecall}%`,    color: parseInt(computedRecall) >= 85 ? "#22c55e" : "#ef4444" },
              { label: "Computed FPR",            value: `${computedFPR}%`,       color: parseFloat(computedFPR) <= 1 ? "#22c55e" : "#ef4444" },
              { label: "Computed Block Rate",     value: `${computedBlockRate}%`, color: "#f97316" },
            ].map(r => (
              <div key={r.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, padding: "3px 0" }}>
                <span style={{ color: "#718096" }}>{r.label}</span>
                <span style={{ fontWeight: 700, color: r.color }}>{r.value}</span>
              </div>
            ))}
          </div>

          {/* Tier thresholds */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {[
              { label: "SAFE",       cutoff: "< 0.50",                    color: "#22c55e" },
              { label: "SUSPICIOUS", cutoff: "0.50 – 0.75",               color: "#eab308" },
              { label: "HIGH",       cutoff: "0.75 – 0.90",               color: "#f97316" },
              { label: "BLOCK",      cutoff: `≥ ${threshold.toFixed(2)}`, color: "#ef4444" },
            ].map(t => (
              <div key={t.label} style={{ display: "flex", justifyContent: "space-between", background: "#0d1117", borderRadius: 6, padding: "7px 10px", border: `1px solid ${t.color}22` }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: t.color }}>{t.label}</span>
                <span style={{ fontSize: 11, color: "#718096", fontFamily: "monospace" }}>{t.cutoff}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 10, fontSize: 10, color: "#4a5568" }}>
            Computed from {withLabels.length} labeled transactions currently in memory.
          </div>
        </div>

        {/* Drift Monitor */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", textTransform: "uppercase", letterSpacing: "0.07em" }}>
            Model Drift Monitor
          </div>

          {[
            { label: "Drift Status",     value: sysMetrics?.drift_status || "Stable",   color: sysMetrics?.drift_status === "Stable" ? "#22c55e" : sysMetrics?.drift_status === "Warning" ? "#f97316" : "#ef4444" },
            { label: "PSI Score",        value: sysMetrics?.drift_psi ?? "—",            sub: "PSI > 0.10 Warning | > 0.20 Critical", color: (sysMetrics?.drift_psi || 0) < 0.10 ? "#22c55e" : (sysMetrics?.drift_psi || 0) < 0.20 ? "#f97316" : "#ef4444" },
            { label: "Fraud Pressure",   value: sysMetrics?.fraud_pressure || "LOW",     color: sysMetrics?.fraud_pressure === "HIGH" ? "#ef4444" : sysMetrics?.fraud_pressure === "MEDIUM" ? "#f97316" : "#22c55e" },
            { label: "SLA Breach %",     value: `${sysMetrics?.sla_breach_pct ?? 0}%`,  sub: "Target < 5%", color: (sysMetrics?.sla_breach_pct || 0) < 5 ? "#22c55e" : "#ef4444" },
            { label: "Alerts / min",     value: sysMetrics?.alerts_per_min ?? 0,        color: "#f97316" },
            { label: "FPR (live)",       value: `${sysMetrics?.fpr ?? 0}%`,              sub: "Target ≤ 1.0%", color: (sysMetrics?.fpr || 0) <= 1 ? "#22c55e" : "#ef4444" },
            { label: "Recall (live)",    value: `${sysMetrics?.recall ?? 0}%`,           sub: "Target ≥ 85%", color: (sysMetrics?.recall || 0) >= 85 ? "#22c55e" : "#ef4444" },
          ].map(d => (
            <MetricTile key={d.label} label={d.label} value={d.value} sub={d.sub} color={d.color} />
          ))}
        </div>
      </div>
    </div>
  )
}
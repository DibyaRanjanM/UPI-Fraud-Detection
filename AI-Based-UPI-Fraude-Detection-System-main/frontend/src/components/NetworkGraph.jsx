import { useState, useEffect, useRef } from "react"
import ForceGraph2D from "react-force-graph-2d"

const API = "http://localhost:8000"

// Unified tier colour map — covers both old + new tier labels
const TIER_COLOR = {
  BLOCK:       "#ef4444",
  HIGH:        "#f97316",
  SUSPICIOUS:  "#eab308",
  SAFE:        "#22c55e",
  Block:       "#ef4444",
  "High-Risk": "#f97316",
  Suspicious:  "#eab308",
  Legitimate:  "#22c55e",
}

const isHighRisk = tier => ["BLOCK", "HIGH", "Block", "High-Risk"].includes(tier)
const isSuspicious = tier => ["SUSPICIOUS", "Suspicious"].includes(tier)

export default function NetworkGraph() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selected, setSelected]   = useState(null)
  const [animTick, setAnimTick]   = useState(0)
  const [filterTier, setFilterTier] = useState("ALL")
  const fgRef = useRef()
  const nodePositions = useRef({})  // Persist node x,y across fetches

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        const res  = await fetch(`${API}/graph/data`)
        const data = await res.json()
        if (!data.nodes || data.nodes.length === 0) return

        // Merge: preserve existing node positions so the graph doesn't explode
        const mergedNodes = data.nodes.map(n => {
          const prev = nodePositions.current[n.id]
          if (prev) {
            return { ...n, x: prev.x, y: prev.y, vx: 0, vy: 0 }
          }
          return n
        })

        setGraphData({ nodes: mergedNodes, links: data.links })
      } catch (e) { console.error(e) }
    }
    fetchGraph()
    const id = setInterval(fetchGraph, 8000)
    return () => clearInterval(id)
  }, [])

  // Save node positions whenever simulation ticks
  useEffect(() => {
    graphData.nodes.forEach(n => {
      if (n.x !== undefined && n.y !== undefined) {
        nodePositions.current[n.id] = { x: n.x, y: n.y }
      }
    })
  }, [graphData])

  // Animation tick for pulsing nodes and forwarding chains
  useEffect(() => {
    const id = setInterval(() => setAnimTick(t => (t + 1) % 120), 50)
    return () => clearInterval(id)
  }, [])

  // Filtered graph data
  const filteredData = {
    nodes: filterTier === "ALL" ? graphData.nodes : graphData.nodes.filter(n => {
      if (filterTier === "BLOCK")      return ["BLOCK","Block"].includes(n.risk_tier)
      if (filterTier === "HIGH")       return ["HIGH","High-Risk"].includes(n.risk_tier)
      if (filterTier === "SUSPICIOUS") return ["SUSPICIOUS","Suspicious"].includes(n.risk_tier)
      return true
    }),
    links: graphData.links,
  }

  const nodeCanvasObject = (node, ctx, globalScale) => {
    const color    = TIER_COLOR[node.risk_tier] || "#718096"
    const isHigh   = isHighRisk(node.risk_tier)
    const isSusp   = isSuspicious(node.risk_tier)
    const isStar   = node.is_star_receiver
    const isCluster = node.is_suspicious_cluster
    const isChain  = (node.chain_length || 0) >= 4
    const baseSize = Math.max(4, Math.min(20, (node.pagerank || 0) * 7000 + 5))

    // Pulsing for high-risk nodes
    const pulse    = isHigh ? Math.sin(animTick * 0.15) * 3 : isSusp ? Math.sin(animTick * 0.1) * 1.5 : 0
    const size     = baseSize + pulse

    // ── Suspicious cluster: red background ring (PDF requirement) ──────────
    if (isCluster || isStar) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 8, 0, 2 * Math.PI)
      ctx.fillStyle = "#ef444418"
      ctx.fill()
      ctx.strokeStyle = "#ef4444"
      ctx.lineWidth   = 1.5
      ctx.setLineDash([4, 3])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // ── Rapid forwarding chain: pulsing orange ring (PDF requirement) ──────
    if (isChain) {
      const chainPulse = 0.4 + Math.sin(animTick * 0.25) * 0.3
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 5, 0, 2 * Math.PI)
      ctx.strokeStyle = `rgba(249,115,22,${chainPulse})`
      ctx.lineWidth   = 2.5
      ctx.stroke()
    }

    // ── High-risk outer glow ───────────────────────────────────────────────
    if (isHigh) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI)
      ctx.fillStyle = color + "20"
      ctx.fill()
    }

    // ── Main node circle ───────────────────────────────────────────────────
    ctx.beginPath()
    ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
    ctx.fillStyle = color + "30"
    ctx.fill()
    ctx.strokeStyle = color
    ctx.lineWidth   = isHigh ? 2.5 : isSusp ? 1.5 : 1
    ctx.stroke()

    // ── Known fraud proximity indicator ───────────────────────────────────
    if (node.fraud_hop_count === 1) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size - 3, 0, 2 * Math.PI)
      ctx.fillStyle = "#ef4444"
      ctx.fill()
    }

    // ── Label on zoom ─────────────────────────────────────────────────────
    if (globalScale > 1.3) {
      ctx.font      = `${10 / globalScale}px monospace`
      ctx.fillStyle = "#a0aec0"
      ctx.textAlign = "center"
      ctx.fillText(node.label || "", node.x, node.y + size + 8 / globalScale)
    }
  }

  const linkCanvasObject = (link, ctx) => {
    const color    = TIER_COLOR[link.risk_tier] || "#2d3748"
    const isChain  = link.is_chain
    const width    = Math.min(4, Math.max(0.5, (link.amount || 0) / 20000))

    if (isChain) {
      // Pulsing orange for forwarding chains
      const alpha = 0.3 + Math.sin(animTick * 0.25) * 0.3
      ctx.strokeStyle = `rgba(249,115,22,${alpha})`
      ctx.lineWidth   = 3
    } else {
      ctx.strokeStyle = color + "66"
      ctx.lineWidth   = width
    }
  }

  // Network tier stats
  const tierCounts = graphData.nodes.reduce((acc, n) => {
    const k = ["BLOCK","Block"].includes(n.risk_tier) ? "BLOCK"
             : ["HIGH","High-Risk"].includes(n.risk_tier) ? "HIGH"
             : ["SUSPICIOUS","Suspicious"].includes(n.risk_tier) ? "SUSPICIOUS" : "SAFE"
    acc[k] = (acc[k] || 0) + 1
    return acc
  }, {})

  const clusterCount = graphData.nodes.filter(n => n.is_suspicious_cluster || n.is_star_receiver).length
  const chainCount   = graphData.nodes.filter(n => (n.chain_length || 0) >= 4).length

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 14, height: "calc(100vh - 120px)" }}>

      {/* Graph Canvas */}
      <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "10px 14px", borderBottom: "1px solid #30363d", fontSize: 11, fontWeight: 600, color: "#a0aec0", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span>Transaction Network Graph</span>
          <span style={{ fontSize: 10, color: "#4a5568" }}>{filteredData.nodes.length} VPAs · {graphData.links.length} edges</span>

          {/* Filter buttons */}
          <div style={{ display: "flex", gap: 4, marginLeft: 8 }}>
            {["ALL","BLOCK","HIGH","SUSPICIOUS"].map(f => (
              <button key={f} onClick={() => setFilterTier(f)} style={{
                padding: "2px 8px", borderRadius: 4, fontSize: 9, fontWeight: 700, cursor: "pointer",
                background: filterTier === f ? (f === "ALL" ? "#1f2937" : TIER_COLOR[f] + "33") : "transparent",
                color: f === "ALL" ? "#a0aec0" : TIER_COLOR[f] || "#a0aec0",
                border: `1px solid ${f === "ALL" ? "#30363d" : TIER_COLOR[f] || "#30363d"}`,
              }}>{f}</button>
            ))}
          </div>

          {/* Legend */}
          <div style={{ marginLeft: "auto", display: "flex", gap: 10, flexWrap: "wrap" }}>
            {[["BLOCK","#ef4444"],["HIGH","#f97316"],["SUSPICIOUS","#eab308"],["SAFE","#22c55e"]].map(([tier, color]) => (
              <span key={tier} style={{ fontSize: 9, color, display: "flex", alignItems: "center", gap: 3 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, display: "inline-block" }} />
                {tier}
              </span>
            ))}
            <span style={{ fontSize: 9, color: "#ef4444", display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", border: "1.5px dashed #ef4444", display: "inline-block" }} />
              CLUSTER
            </span>
            <span style={{ fontSize: 9, color: "#f97316", display: "flex", alignItems: "center", gap: 3 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", border: "2px solid #f97316", display: "inline-block" }} />
              CHAIN
            </span>
          </div>
        </div>

        <ForceGraph2D
          ref={fgRef}
          graphData={filteredData}
          backgroundColor="#0d1117"
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => "replace"}
          linkColor={link => (TIER_COLOR[link.risk_tier] || "#2d3748") + "55"}
          linkWidth={link => Math.min(4, Math.max(0.5, (link.amount || 0) / 20000))}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={link => ["BLOCK","Block"].includes(link.risk_tier) ? 3 : 0}
          linkDirectionalParticleColor={link => TIER_COLOR[link.risk_tier] || "#fff"}
          linkDirectionalParticleWidth={2}
          onNodeClick={node => setSelected(node)}
          width={window.innerWidth - 380}
          height={window.innerHeight - 170}
          cooldownTicks={50}
          cooldownTime={1500}
          warmupTicks={30}
          d3AlphaDecay={0.05}
          d3VelocityDecay={0.4}
          onEngineStop={() => {
            // Save final positions after simulation settles
            if (fgRef.current) {
              graphData.nodes.forEach(n => {
                if (n.x !== undefined) nodePositions.current[n.id] = { x: n.x, y: n.y }
              })
            }
          }}
          nodeLabel={node =>
            `${node.label || node.id}\nTier: ${node.risk_tier}\nTxns: ${node.txn_count}\nPageRank: ${(node.pagerank||0).toFixed(6)}\nCommunity: ${node.community_id ?? "—"}\nChain Len: ${node.chain_length ?? 0}`
          }
        />
      </div>

      {/* Right Panel */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

        {/* Node Detail */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px", flex: 1, overflow: "auto" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 12 }}>Node Details</div>
          {!selected
            ? <div style={{ color: "#4a5568", fontSize: 12 }}>Click a node to inspect</div>
            : (() => {
                const color = TIER_COLOR[selected.risk_tier] || "#718096"
                return (
                  <div>
                    <div style={{ fontSize: 10, color: "#4a5568", marginBottom: 3 }}>VPA</div>
                    <div style={{ fontSize: 11, color: "#e2e8f0", marginBottom: 12, wordBreak: "break-all", fontFamily: "monospace" }}>{selected.label}</div>

                    <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
                      <span style={{ background: color + "22", color, border: `1px solid ${color}`, borderRadius: 4, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
                        {selected.risk_tier}
                      </span>
                      {selected.is_suspicious_cluster && <span style={{ background: "#ef444422", color: "#ef4444", border: "1px dashed #ef4444", borderRadius: 4, padding: "2px 6px", fontSize: 9, fontWeight: 700 }}>CLUSTER</span>}
                      {(selected.chain_length || 0) >= 4 && <span style={{ background: "#f9731622", color: "#f97316", border: "1px solid #f97316", borderRadius: 4, padding: "2px 6px", fontSize: 9, fontWeight: 700 }}>CHAIN</span>}
                      {selected.is_star_receiver && <span style={{ background: "#ef444422", color: "#ef4444", border: "1px solid #ef4444", borderRadius: 4, padding: "2px 6px", fontSize: 9, fontWeight: 700 }}>MULE STAR</span>}
                    </div>

                    {[
                      ["PageRank",      (selected.pagerank || 0).toFixed(6)],
                      ["Txn Count",     selected.txn_count || 0],
                      ["Community ID",  selected.community_id ?? "—"],
                      ["Chain Length",  selected.chain_length ?? 0],
                      ["Fraud Hop",     selected.fraud_hop_count === -1 ? "Not linked" : selected.fraud_hop_count ?? "—"],
                    ].map(([k, v]) => (
                      <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #1e2538", fontSize: 11 }}>
                        <span style={{ color: "#718096" }}>{k}</span>
                        <span style={{ color: "#e2e8f0", fontWeight: 600, fontFamily: "monospace" }}>{v}</span>
                      </div>
                    ))}

                    {selected.fraud_hop_count === 1 && (
                      <div style={{ marginTop: 10, background: "#2d1515", border: "1px solid #ef4444", borderRadius: 6, padding: 10, fontSize: 11, color: "#fc8181" }}>
                        ⚠ Direct 1-hop connection to confirmed fraud VPA. Immediate BLOCK recommended.
                      </div>
                    )}
                    {selected.is_suspicious_cluster && (
                      <div style={{ marginTop: 8, background: "#2d1515", border: "1px dashed #ef4444", borderRadius: 6, padding: 10, fontSize: 11, color: "#fc8181" }}>
                        ⚠ Node is part of a suspicious community cluster detected by Louvain algorithm.
                      </div>
                    )}
                    {(selected.chain_length || 0) >= 4 && (
                      <div style={{ marginTop: 8, background: "#2d1e0f", border: "1px solid #f97316", borderRadius: 6, padding: 10, fontSize: 11, color: "#fdba74" }}>
                        ⚠ Rapid fund forwarding chain of {selected.chain_length} hops detected. Possible money laundering.
                      </div>
                    )}
                  </div>
                )
              })()
          }
        </div>

        {/* Network Stats */}
        <div style={{ background: "#161B22", border: "1px solid #30363d", borderRadius: 10, padding: "14px 16px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#a0aec0", marginBottom: 10 }}>Network Summary</div>
          {[
            { label: "BLOCK nodes",       value: tierCounts.BLOCK || 0,   color: "#ef4444" },
            { label: "HIGH nodes",        value: tierCounts.HIGH  || 0,   color: "#f97316" },
            { label: "SUSPICIOUS nodes",  value: tierCounts.SUSPICIOUS || 0, color: "#eab308" },
            { label: "SAFE nodes",        value: tierCounts.SAFE  || 0,   color: "#22c55e" },
            { label: "Suspicious clusters", value: clusterCount, color: "#ef4444" },
            { label: "Forwarding chains", value: chainCount,            color: "#f97316" },
          ].map(({ label, value, color }) => {
            const total = graphData.nodes.length || 1
            const pct   = Math.round(value / total * 100)
            return (
              <div key={label} style={{ marginBottom: 7 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ fontSize: 10, color }}>{label}</span>
                  <span style={{ fontSize: 10, color: "#718096" }}>{value} ({pct}%)</span>
                </div>
                <div style={{ height: 3, background: "#0d1117", borderRadius: 2 }}>
                  <div style={{ height: 3, width: `${pct}%`, background: color, borderRadius: 2 }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
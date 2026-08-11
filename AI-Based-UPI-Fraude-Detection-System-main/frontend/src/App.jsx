import React, { useState, useEffect } from "react";
import FraudOpsCenter from "./components/FraudOpsCenter";
import NetworkGraph from "./components/NetworkGraph";
import ModelPerformance from "./components/ModelPerformance";
import TransactionInvestigator from "./components/TransactionInvestigator";
import SystemHealth from "./components/SystemHealth";

const API = "http://localhost:8000";

const TABS = [
  { id: "ops",    label: "Live Ops",       icon: "◉" },
  { id: "graph",  label: "Fraud Graph",    icon: "◎" },
  { id: "model",  label: "Explainability", icon: "◈" },
  { id: "search", label: "Deep Dive",      icon: "⌕" },
  { id: "health", label: "System Health",  icon: "◍" },
];

export default function App() {
  const [tab, setTab]       = useState("ops");
  const [health, setHealth] = useState({ alerts: 0, txns: 0 });
  const [pressure, setPressure] = useState("LOW");
  const [sessionTime, setSessionTime] = useState(0);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const [h, s] = await Promise.all([
          fetch(`${API}/health`).then(r => r.json()),
          fetch(`${API}/metrics/system`).then(r => r.json()),
        ]);
        setHealth(h);
        setPressure(s.fraud_pressure || "LOW");
      } catch (_) {}
    };
    fetchHealth();
    const id = setInterval(fetchHealth, 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const id = setInterval(() => setSessionTime(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const fmtTime = s => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return `${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`;
  };

  const pressureColor = pressure === "HIGH" ? "#ef4444" : pressure === "MEDIUM" ? "#f97316" : "#22c55e";

  return (
    <div className="flex h-screen bg-[#060B17] text-[#c9d1d9] font-sans antialiased overflow-hidden p-3">

      {/* LEFT SIDEBAR */}
      <div className="w-64 bg-[#091428] border border-[#17315e] rounded-l-xl flex flex-col justify-between hidden md:flex shrink-0 shadow-[0_0_30px_rgba(0,229,255,0.06)]">
        <div>
          {/* Branding */}
          <div className="px-6 py-7 border-b border-[#17315e] mb-4">
            <h1 className="text-xl font-black tracking-widest text-[#e8f2ff]">SENTINEL</h1>
            <h2 className="text-[10px] font-mono tracking-[0.3em] text-[#27d3ff]" style={{ textShadow: "0 0 12px rgba(39,211,255,0.45)" }}>
              MONITORING SUITE
            </h2>
          </div>

          {/* Node status */}
          <div className="px-4 py-3 border-b border-[#17315e] mb-4 text-xs font-mono text-gray-500">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 rounded-full bg-[#00E5FF]" style={{ boxShadow: "0 0 6px #00E5FF" }}></span>
              <span className="text-gray-300 text-[10px] tracking-widest">NODE_01 · ACTIVE</span>
            </div>
            <div className="text-[10px] text-gray-500">Session: {fmtTime(sessionTime)}</div>
            <div className="flex justify-between mt-2">
              <span className="text-[10px]">
                Alerts: <span style={{ color: health.alerts > 50 ? "#ef4444" : "#22c55e" }}>{health.alerts}</span>
              </span>
              <span className="text-[10px]">
                Scored: <span className="text-[#63b3ed]">{health.txns?.toLocaleString()}</span>
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[10px] text-gray-500">Pressure:</span>
              <span className="text-[10px] font-bold" style={{ color: pressureColor }}>{pressure}</span>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex flex-col gap-1 px-3">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm text-left transition-all ${
                  tab === t.id
                    ? "bg-[#112647] text-white font-semibold border-l-2 border-[#00E5FF]"
                    : "text-gray-400 hover:text-gray-200 hover:bg-[#0d203d]"
                }`}
              >
                <span>{t.icon}</span>
                {t.label}
                {/* Active pulse for ops tab */}
                {t.id === "ops" && (
                  <span className="ml-auto w-2 h-2 rounded-full bg-[#22c55e]" style={{ animation: "pulse 1.4s infinite" }}></span>
                )}
              </button>
            ))}
          </nav>
        </div>

        {/* Bottom */}
        <div className="p-4 border-t border-[#17315e]">
          <div className="flex flex-col gap-2 mb-5 text-xs text-gray-400">
            <button className="text-left hover:text-white px-2 py-1 rounded hover:bg-[#1f2937] transition-colors">📋 Audit Logs</button>
            <button className="text-left hover:text-white px-2 py-1 rounded hover:bg-[#1f2937] transition-colors">📖 Documentation</button>
          </div>
          <button className="w-full bg-[#ef4444] hover:bg-red-700 text-white font-black py-3 rounded text-xs tracking-widest uppercase transition-colors" style={{ boxShadow: "0 0 12px rgba(239,68,68,0.3)" }}>
            ⚡ EMERGENCY SHUTDOWN
          </button>
        </div>
      </div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex flex-col min-w-0 bg-[#050D1F] border-y border-r border-[#17315e] rounded-r-xl">

        {/* Topbar */}
        <div className="h-14 border-b border-[#17315e] bg-[#091428] flex items-center justify-between px-6 shrink-0">
          <div className="flex gap-5 text-[10px] font-mono tracking-widest uppercase text-gray-500">
            {TABS.map(t => (
              <span
                key={t.id}
                onClick={() => setTab(t.id)}
                className="cursor-pointer hover:text-gray-200 transition-colors"
                style={tab === t.id ? { color: "#00E5FF", borderBottom: "2px solid #00E5FF", paddingBottom: 4 } : {}}
              >
                {t.label}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-4">
            {/* Live ticker */}
            <div className="text-[10px] font-mono text-gray-500 hidden lg:flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" style={{ animation: "pulse 1s infinite" }}></span>
              STREAMING ACTIVE
            </div>
            <span className="text-lg cursor-pointer hover:text-white">◔</span>
            <span className="text-lg cursor-pointer hover:text-white">⌬</span>
            <div className="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center text-sm border-2 border-[#17315e]">AI</div>
          </div>
        </div>

        {/* View Router */}
        <div className="flex-1 overflow-hidden p-5 bg-[#050D1F]">
          {tab === "ops"    && <FraudOpsCenter />}
          {tab === "graph"  && <NetworkGraph />}
          {tab === "model"  && <ModelPerformance />}
          {tab === "search" && <TransactionInvestigator />}
          {tab === "health" && <SystemHealth />}
        </div>
      </div>
    </div>
  );
}
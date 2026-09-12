import { useState } from "react";
import Status from "./Status";
import Threats from "./Threats";
import ThreatDetails from "./ThreatDetails";
import PlannerView from "./PlannerView";
import GlobeView from "./GlobeView";
import Scrubber from "./Scrubber";
import AgentFeed from "./AgentFeed";
import LedgerTable from "./LedgerTable";

export default function App() {
  const [selectedCdmId, setSelectedCdmId] = useState("CDM-0001");
  const [activeTab, setActiveTab] = useState("DETAILS"); // "DETAILS" | "PLANNER" | "NONE"
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [ephemerisMeta, setEphemerisMeta] = useState({
    epochs: [],
    tca: "",
    tcaIndex: 0,
  });

  const handleEphemerisLoaded = ({ epochs, tca, tcaIndex }) => {
    setEphemerisMeta({ epochs, tca, tcaIndex });
    setCurrentIndex(0);
  };

  const [selectedThreatSummary, setSelectedThreatSummary] = useState(null);

  const handleSelectThreat = (id, summary) => {
    setSelectedCdmId(id);
    setSelectedThreatSummary(summary || null);
    if (activeTab === "NONE") {
      setActiveTab("DETAILS");
    }
    setIsPlaying(false);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#070A0F] text-[#C8D4E0] overflow-hidden">
      {/* Top Telemetry Status Bar */}
      <Status />

      {/* Navigation Sub-header / Mode Switcher */}
      <div className="bg-[#0E141C] border-b border-[#1E2833] px-4 py-1.5 flex items-center justify-between font-mono text-xs z-10">
        <div className="flex items-center gap-2">
          <span className="text-[#6B7A8C] font-bold text-[10px] uppercase tracking-wider">VIEW MODE:</span>
          <button
            onClick={() => setActiveTab("DETAILS")}
            className={`px-3 py-1 rounded text-xs font-bold transition-colors cursor-pointer ${
              activeTab === "DETAILS"
                ? "bg-[#1E2833] text-white border border-[#6B7A8C]/50"
                : "hover:bg-[#1E2833]/50 text-[#6B7A8C]"
            }`}
          >
            📋 THREAT ANALYTICS
          </button>
          <button
            onClick={() => setActiveTab("PLANNER")}
            className={`px-3 py-1 rounded text-xs font-bold transition-colors cursor-pointer ${
              activeTab === "PLANNER"
                ? "bg-emerald-950 text-[#3DD68C] border border-emerald-800/50"
                : "hover:bg-[#1E2833]/50 text-[#6B7A8C]"
            }`}
          >
            🚀 AVOIDANCE PLANNER
          </button>
          <button
            onClick={() => setActiveTab("LEDGER")}
            className={`px-3 py-1 rounded text-xs font-bold transition-colors cursor-pointer ${
              activeTab === "LEDGER"
                ? "bg-blue-950 text-blue-400 border border-blue-800/50"
                : "hover:bg-[#1E2833]/50 text-[#6B7A8C]"
            }`}
          >
            🔗 INTENT LEDGER
          </button>
        </div>

        <div className="text-[11px] text-[#6B7A8C]">
          SELECTED THREAT: <span className="text-[#3DD68C] font-bold">{selectedCdmId}</span>
        </div>
      </div>

      {/* Main Mission Operations Dashboard Area */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        {/* Left Panel: Conjunction Threats List */}
        <Threats
          selectedId={selectedCdmId}
          onSelectThreat={handleSelectThreat}
        />

        {/* Panel Popup / Drawer (Threat Details vs Planner View vs Ledger Table) */}
        {activeTab === "DETAILS" && (
          <ThreatDetails
            conjunctionId={selectedCdmId}
            threatSummary={selectedThreatSummary}
            onClose={() => setActiveTab("NONE")}
          />
        )}

        {activeTab === "PLANNER" && (
          <PlannerView
            cdmId={selectedCdmId}
            onClose={() => setActiveTab("NONE")}
          />
        )}

        {activeTab === "LEDGER" && (
          <LedgerTable
            onClose={() => setActiveTab("NONE")}
          />
        )}


        {/* Center/Right Panel: 3D Earth Globe + Time Scrubber */}
        <div className="flex-1 flex flex-col h-full relative overflow-hidden">
          {/* 3D Globe Visualization */}
          <div className="flex-1 min-h-0 relative">
            <GlobeView
              selectedCdmId={selectedCdmId}
              currentIndex={currentIndex}
              onEphemerisLoaded={handleEphemerisLoaded}
            />
          </div>

          {/* Time Scrubber Bar under Globe */}
          <Scrubber
            epochs={ephemerisMeta.epochs}
            currentIndex={currentIndex}
            tcaIndex={ephemerisMeta.tcaIndex}
            tcaTime={ephemerisMeta.tca}
            onIndexChange={setCurrentIndex}
            isPlaying={isPlaying}
            onTogglePlay={() => setIsPlaying((prev) => !prev)}
          />
        </div>
      </div>

      {/* Bottom Live Agent Reasoning & Tool Stream Feed */}
      <AgentFeed selectedCdmId={selectedCdmId} />
    </div>
  );
}



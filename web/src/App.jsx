import { useState } from "react";
import Status from "./Status";
import Threats from "./Threats";
import ThreatDetails from "./ThreatDetails";
import GlobeView from "./GlobeView";
import Scrubber from "./Scrubber";

export default function App() {
  const [selectedCdmId, setSelectedCdmId] = useState("CDM-0001");
  const [showDetails, setShowDetails] = useState(true);
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
    setShowDetails(true);
    setIsPlaying(false);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#070A0F] text-[#C8D4E0] overflow-hidden">
      {/* Top Telemetry Status Bar */}
      <Status />

      {/* Main Mission Operations Dashboard Area */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Left Panel: Conjunction Threats List */}
        <Threats
          selectedId={selectedCdmId}
          onSelectThreat={handleSelectThreat}
        />

        {/* Threat Details Panel Popup / Drawer (to the right of Threat List) */}
        {showDetails && (
          <ThreatDetails
            conjunctionId={selectedCdmId}
            threatSummary={selectedThreatSummary}
            onClose={() => setShowDetails(false)}
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
    </div>
  );
}

import { useEffect } from "react";

export default function Scrubber({
  epochs = [],
  currentIndex = 0,
  tcaIndex = 0,
  tcaTime = "",
  onIndexChange,
  isPlaying = false,
  onTogglePlay,
}) {
  // Auto-play timer
  useEffect(() => {
    let interval = null;
    if (isPlaying && epochs.length > 0) {
      interval = setInterval(() => {
        onIndexChange((prev) => {
          if (prev >= epochs.length - 1) return 0;
          return prev + 1;
        });
      }, 100); // Advance 1 step every 100ms
    }
    return () => clearInterval(interval);
  }, [isPlaying, epochs.length, onIndexChange]);

  const maxIndex = Math.max(0, epochs.length - 1);
  const currentEpoch = epochs[currentIndex] || "—";
  const tcaPercent = maxIndex > 0 ? (tcaIndex / maxIndex) * 100 : 0;

  // Format relative time offset from TCA
  const getRelativeTcaTime = () => {
    if (!epochs[currentIndex] || !tcaTime) return "";
    const diffMs = new Date(epochs[currentIndex]) - new Date(tcaTime);
    const diffSec = Math.floor(diffMs / 1000);
    const sign = diffSec >= 0 ? "+" : "-";
    const absSec = Math.abs(diffSec);
    const hours = String(Math.floor(absSec / 3600)).padStart(2, "0");
    const mins = String(Math.floor((absSec % 3600) / 60)).padStart(2, "0");
    const secs = String(absSec % 60).padStart(2, "0");
    return `TCA ${sign}${hours}:${mins}:${secs}`;
  };

  return (
    <div className="w-full bg-[#0E141C] border-t border-[#1E2833] p-3 font-mono text-xs text-[#C8D4E0] flex flex-col gap-2 shadow-2xl z-20">
      {/* Top Control Bar: Controls + Timestamps */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Play/Pause Button */}
          <button
            onClick={onTogglePlay}
            className="px-3 py-1 bg-[#1E2833] hover:bg-[#283545] border border-[#6B7A8C]/40 text-[#C8D4E0] font-bold rounded flex items-center gap-1.5 transition-all text-xs cursor-pointer"
          >
            {isPlaying ? "❚❚ PAUSE" : "▶ PLAY"}
          </button>

          {/* Jump to TCA Button */}
          <button
            onClick={() => onIndexChange && onIndexChange(tcaIndex)}
            className="px-2.5 py-1 bg-red-950/80 hover:bg-red-900/80 border border-red-800/60 text-[#E5484D] font-bold rounded transition-all text-[11px] flex items-center gap-1 cursor-pointer"
          >
            🎯 SNAP TO TCA
          </button>
        </div>

        {/* Timestamp Info */}
        <div className="flex items-center gap-4 text-xs">
          <div>
            EPOCH: <span className="text-white font-bold">{currentEpoch}</span>
          </div>
          <div className="px-2 py-0.5 rounded bg-[#1E2833] text-[#E8A33D] font-bold border border-[#1E2833]">
            {getRelativeTcaTime() || "TCA MATCH"}
          </div>
        </div>
      </div>

      {/* Slider Track Container */}
      <div className="relative w-full flex items-center py-1">
        {/* TCA Marker Line */}
        {maxIndex > 0 && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-[#E5484D] z-10 pointer-events-none"
            style={{ left: `${tcaPercent}%` }}
            title={`TCA Event at index ${tcaIndex}`}
          >
            <span className="absolute -top-4 -left-3 text-[9px] font-bold text-[#E5484D] bg-[#070A0F] px-1 rounded border border-[#E5484D]/40">
              TCA
            </span>
          </div>
        )}

        {/* Range Slider */}
        <input
          type="range"
          min={0}
          max={maxIndex}
          value={currentIndex}
          onChange={(e) => onIndexChange && onIndexChange(Number(e.target.value))}
          className="w-full accent-[#3DD68C] bg-[#1E2833] h-2 rounded-lg cursor-pointer appearance-none"
        />
      </div>

      {/* Progress Footer */}
      <div className="flex items-center justify-between text-[10px] text-[#6B7A8C]">
        <span>STEP: {currentIndex} / {maxIndex}</span>
        <span>STEP SIZE: 60s</span>
      </div>
    </div>
  );
}

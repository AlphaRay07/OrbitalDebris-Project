export default function PcChart({ data = [] }) {
  if (!data || data.length === 0) {
    return (
      <div className="text-[#6B7A8C] text-xs font-mono p-4">
        No Pc history telemetry available.
      </div>
    );
  }

  const width = 360;
  const height = 160;
  const padding = 35;

  const threshold = 0.0001; // RED threshold 1e-4

  const pcValues = data.map((d) => d.pc);
  const minPc = Math.min(...pcValues, 1e-6);
  const maxPc = Math.max(...pcValues, 0.0005);

  const getX = (index) => {
    return (
      padding + (index / (data.length - 1)) * (width - padding * 2)
    );
  };

  const getY = (pc) => {
    // Log scale y-axis mapping
    const minLog = Math.log10(minPc);
    const maxLog = Math.log10(maxPc);
    const valLog = Math.log10(Math.max(pc, 1e-7));
    const ratio = (valLog - minLog) / (maxLog - minLog);
    return height - padding - ratio * (height - padding * 2);
  };

  const pointsString = data
    .map((d, i) => `${getX(i)},${getY(d.pc)}`)
    .join(" ");

  const thresholdY = getY(threshold);

  return (
    <div className="flex flex-col gap-1.5 font-mono text-xs">
      <div className="flex items-center justify-between text-[10px] text-[#6B7A8C] font-bold uppercase tracking-wider">
        <span>COLLISION PROBABILITY (P<sub>c</sub> HISTORY)</span>
        <span className="text-[#E5484D]">RED THRESHOLD: 1e-4</span>
      </div>

      <div className="w-full bg-[#070A0F] border border-[#1E2833] rounded-lg p-2 relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
          {/* Threshold Line 1e-4 */}
          <line
            x1={padding}
            y1={thresholdY}
            x2={width - padding}
            y2={thresholdY}
            stroke="#E5484D"
            strokeDasharray="4 4"
            strokeWidth="1.5"
          />
          <text
            x={width - padding - 45}
            y={thresholdY - 4}
            fill="#E5484D"
            fontSize="9"
            fontWeight="bold"
          >
            1e-4 RED
          </text>

          {/* Area under line */}
          <polygon
            points={`${getX(0)},${height - padding} ${pointsString} ${getX(
              data.length - 1
            )},${height - padding}`}
            fill="rgba(229, 72, 77, 0.15)"
          />

          {/* Pc Line */}
          <polyline
            fill="none"
            stroke="#E8A33D"
            strokeWidth="2.5"
            points={pointsString}
          />

          {/* Data Points */}
          {data.map((d, i) => {
            const cx = getX(i);
            const cy = getY(d.pc);
            const isAboveThreshold = d.pc >= threshold;
            return (
              <g key={i}>
                <circle
                  cx={cx}
                  cy={cy}
                  r="3.5"
                  fill={isAboveThreshold ? "#E5484D" : "#E8A33D"}
                  stroke="#FFFFFF"
                  strokeWidth="1.5"
                />
              </g>
            );
          })}

          {/* X Axis */}
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="#1E2833"
            strokeWidth="1.5"
          />

          {/* X Axis Labels */}
          {data.map((d, i) => {
            if (i === 0 || i === Math.floor(data.length / 2) || i === data.length - 1) {
              const timeStr = new Date(d.t).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              });
              return (
                <text
                  key={i}
                  x={getX(i)}
                  y={height - 10}
                  fill="#6B7A8C"
                  fontSize="8"
                  textAnchor="middle"
                >
                  {timeStr}
                </text>
              );
            }
            return null;
          })}
        </svg>
      </div>
    </div>
  );
}

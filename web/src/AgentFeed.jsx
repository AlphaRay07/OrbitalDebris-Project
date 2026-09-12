import { useEffect, useState, useRef } from "react";
import { runAgents } from "./api";

const BASE = "http://localhost:8010/api";


export default function AgentFeed({ selectedCdmId }) {
  const [events, setEvents] = useState([]);
  const [expandedResults, setExpandedResults] = useState({});
  const [collapsed, setCollapsed] = useState(false);
  const feedEndRef = useRef(null);
  const containerRef = useRef(null);


  useEffect(() => {
    let es = null;
    let timer = null;

    // Try connecting to live SSE backend endpoint first
    try {
      es = new EventSource(`${BASE}/events`);

      es.onmessage = (e) => {
        try {
          const newEvt = JSON.parse(e.data);
          pushEvent(newEvt);
        } catch (err) {
          console.error("Error parsing SSE event:", err);
        }
      };

      es.onerror = () => {
        // Fallback to static fixtures loop if server event stream is unreachable
        if (es) es.close();
        startFixtureReplay();
      };
    } catch (err) {
      startFixtureReplay();
    }

    function startFixtureReplay() {
      fetch("/fixtures/events.json")
        .then((res) => res.json())
        .then((data) => {
          let idx = 0;
          timer = setInterval(() => {
            if (data && data.length > 0) {
              const item = data[idx % data.length];
              pushEvent({ ...item, seq: Date.now() });
              idx++;
            }
          }, 3500);
        })
        .catch(() => {});
    }

    function pushEvent(evt) {
      setEvents((prev) => {
        const next = [...prev, evt];
        // Keep last 100 events only per guide requirement
        if (next.length > 100) return next.slice(next.length - 100);
        return next;
      });

      // Auto-scroll only when user is already at the bottom
      if (containerRef.current) {
        const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
        const isNearBottom = scrollHeight - scrollTop - clientHeight < 60;
        if (isNearBottom) {
          setTimeout(() => {
            feedEndRef.current?.scrollIntoView({ behavior: "smooth" });
          }, 50);
        }
      }
    }

    // Cleanup on unmount (non-negotiable rule)
    return () => {
      if (es) es.close();
      if (timer) clearInterval(timer);
    };
  }, []);

  const toggleToolResult = (seq) => {
    setExpandedResults((prev) => ({ ...prev, [seq]: !prev[seq] }));
  };

  const getLevelStyle = (level) => {
    switch (level) {
      case "alert":
        return "text-[#E5484D] bg-red-950/60 border-red-800/60";
      case "warn":
        return "text-[#E8A33D] bg-amber-950/60 border-amber-800/60";
      case "info":
      default:
        return "text-[#3DD68C] bg-emerald-950/60 border-emerald-800/60";
    }
  };

  const getAgentBadge = (agent) => {
    switch (agent) {
      case "TRACKER":
        return "bg-blue-900/60 text-blue-300 border-blue-700/50";
      case "SCREENER":
        return "bg-purple-900/60 text-purple-300 border-purple-700/50";
      case "PLANNER":
        return "bg-emerald-900/60 text-emerald-300 border-emerald-700/50";
      case "COORDINATOR":
        return "bg-amber-900/60 text-amber-300 border-amber-700/50";
      default:
        return "bg-gray-800 text-gray-300 border-gray-700";
    }
  };

  return (
    <div className="w-full bg-[#070A0F] border-t border-[#1E2833] font-mono text-xs text-[#C8D4E0] flex flex-col shadow-2xl transition-all duration-300">
      {/* Feed Header */}
      <div className="px-4 py-2 bg-[#0E141C] border-b border-[#1E2833] flex items-center justify-between select-none">
        <div className="flex items-center gap-3">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="font-bold text-white tracking-wider text-[11px]">
            AGENT REASONING & TOOL STREAM (SSE)
          </span>
          <span className="px-1.5 py-0.5 rounded bg-[#1E2833] text-[10px] text-gray-400">
            {events.length} EVENTS
          </span>

          <button
            onClick={() => {
              runAgents(1, selectedCdmId)
                .then((res) => console.log("Agent run started for", selectedCdmId, res))
                .catch((e) => console.error("Agent run error:", e));
            }}
            className="px-2 py-0.5 rounded bg-emerald-950 hover:bg-emerald-900 border border-emerald-700/60 text-[#3DD68C] font-bold text-[10px] cursor-pointer flex items-center gap-1 shadow"
          >
            ▶ RUN AGENT PIPELINE ({selectedCdmId || "CDM-0001"})
          </button>


        </div>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-gray-400 hover:text-white text-[11px] font-semibold px-2 py-0.5 rounded bg-[#1E2833] hover:bg-[#283545] cursor-pointer"
        >
          {collapsed ? "▲ EXPAND FEED" : "▼ COLLAPSE FEED"}
        </button>
      </div>


      {/* Feed Content Body */}
      {!collapsed && (
        <div
          ref={containerRef}
          className="h-44 overflow-y-auto p-3 space-y-2.5 bg-[#070A0F]"
        >
          {events.length === 0 ? (
            <div className="text-gray-500 text-center py-6">
              Connecting to agent SSE stream...
            </div>
          ) : (
            events.map((evt, idx) => {
              const levelStyle = getLevelStyle(evt.level);
              const agentStyle = getAgentBadge(evt.agent);
              const isExpanded = !!expandedResults[evt.seq || idx];

              return (
                <div
                  key={evt.seq || idx}
                  className={`p-2 rounded border ${levelStyle} flex flex-col gap-1.5`}
                >
                  {/* Event Meta Line */}
                  <div className="flex items-center justify-between gap-2 text-[10px]">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-1.5 py-0.2 rounded border font-bold ${agentStyle}`}
                      >
                        {evt.agent || "AGENT"}
                      </span>
                      <span className="text-gray-400">
                        {evt.ts
                          ? new Date(evt.ts).toISOString().substring(11, 19)
                          : "UTC"}
                      </span>
                    </div>

                    <span className="uppercase font-bold tracking-wider text-[9px]">
                      {evt.level}
                    </span>
                  </div>

                  {/* Message Body */}
                  <div className="text-white text-xs leading-relaxed font-sans font-medium">
                    {evt.message}
                  </div>

                  {/* Tool Call & Result Render */}
                  {evt.tool_call && (
                    <div className="mt-1 p-2 bg-[#0E141C] border border-[#1E2833] rounded font-mono text-[11px] text-emerald-400 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-gray-400">tool: </span>
                          <span className="font-bold text-emerald-300">
                            {evt.tool_call.name}
                          </span>
                          <span className="text-gray-400">
                            ({JSON.stringify(evt.tool_call.args)})
                          </span>
                        </div>

                        {evt.tool_result && (
                          <button
                            onClick={() => toggleToolResult(evt.seq || idx)}
                            className="text-[10px] text-gray-400 hover:text-white underline cursor-pointer"
                          >
                            {isExpanded ? "hide result" : "view result"}
                          </button>
                        )}
                      </div>

                      {/* Collapsible Tool Result */}
                      {evt.tool_result && isExpanded && (
                        <pre className="mt-1.5 p-2 bg-[#070A0F] border border-[#1E2833] rounded text-gray-300 text-[10px] overflow-x-auto">
                          {JSON.stringify(evt.tool_result, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
          <div ref={feedEndRef} />
        </div>
      )}
    </div>
  );
}

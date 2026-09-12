import { useRef, useEffect, useState } from "react";
import Globe from "react-globe.gl";
import { getEphemeris, getDebrisCloud } from "./api";

export default function GlobeView({ selectedCdmId = "CDM-0001", currentIndex = 0, onEphemerisLoaded }) {
  const globeRef = useRef();
  const [paths, setPaths] = useState([]);
  const [debris, setDebris] = useState([]);
  const [selectedTrack, setSelectedTrack] = useState(null);
  const [rawTracks, setRawTracks] = useState([]);

  useEffect(() => {
    if (globeRef.current) {
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = false;
        controls.autoRotateSpeed = 2.0;
      }
    }

    // Fetch Orbit Ephemeris Data for the selected CDM event
    getEphemeris(selectedCdmId)
      .then((data) => {
        if (data && data.tracks) {
          setRawTracks(data.tracks);

          const formattedPaths = data.tracks.map((t) => ({
            id: t.object_id,
            role: t.role,
            name: t.name,
            rawTrack: t.track,
            // Decimate for smooth 60fps rendering (every 4th point)
            coords: t.track.filter((_, idx) => idx % 4 === 0),
          }));
          setPaths(formattedPaths);
          if (formattedPaths.length > 0) {
            setSelectedTrack(formattedPaths[0]);
            // Auto-focus camera on satellite position
            if (globeRef.current && formattedPaths[0].coords.length > 0) {
              const [initLat, initLng] = formattedPaths[0].coords[0];
              globeRef.current.pointOfView({ lat: initLat, lng: initLng, altitude: 2.2 }, 1000);
            }
          }

          if (onEphemerisLoaded) {
            onEphemerisLoaded({
              epochs: data.epochs || [],
              tca: data.tca || "",
              tcaIndex: data.tca_index || 0,
            });
          }
        }
      })

      .catch((err) => console.error("Error loading ephemeris:", err));

    // Fetch Debris Cloud Backdrop
    getDebrisCloud()
      .then((data) => {
        if (data && data.points) {
          setDebris(data.points);
        }
      })
      .catch((err) => console.error("Error loading debris cloud:", err));
  }, [selectedCdmId]);

  const handleMouseEnter = () => {
    if (globeRef.current?.controls()) {
      globeRef.current.controls().autoRotate = true;
    }
  };

  const handleMouseLeave = () => {
    if (globeRef.current?.controls()) {
      globeRef.current.controls().autoRotate = false;
    }
  };

  // Compute Current Position markers based on currentIndex from Scrubber
  const currentPositions = rawTracks.map((t) => {
    const point = t.track[Math.min(currentIndex, t.track.length - 1)] || [0, 0, 400];
    return {
      name: t.name,
      role: t.role,
      lat: point[0],
      lng: point[1],
      alt: point[2] / 6371,
      color: t.role === "primary" ? "#3DD68C" : "#E5484D",
    };
  });

  const containerRef = useRef();
  const [dimensions, setDimensions] = useState({ width: 800, height: 500 });

  useEffect(() => {
    if (!containerRef.current) return;
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };

    updateDimensions();
    const resizeObserver = new ResizeObserver(updateDimensions);
    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return (
    <div 
      ref={containerRef}
      onMouseEnter={handleMouseEnter} 
      onMouseLeave={handleMouseLeave} 
      className="w-full h-full relative bg-[#070A0F] border-b border-[#1E2833] overflow-hidden"
    >
      {/* Floating Satellite Clicker HUD */}
      <div className="absolute top-4 left-4 z-10 bg-[#0E141C]/90 backdrop-blur border border-[#1E2833] p-3 rounded-lg text-xs font-mono text-[#C8D4E0] shadow-xl max-w-xs pointer-events-auto">
        <div className="text-[#6B7A8C] text-[10px] uppercase font-bold mb-2 tracking-wider">
          SATELLITE ORBIT SELECTOR
        </div>
        <div className="flex flex-col gap-1.5">
          {paths.map((p) => {
            const isSelected = selectedTrack?.id === p.id;
            return (
              <button
                key={p.id}
                onClick={() => setSelectedTrack(p)}
                className={`flex items-center justify-between px-2.5 py-1.5 rounded transition-all text-left ${
                  isSelected
                    ? "bg-[#1E2833] border border-[#6B7A8C]/50 text-white font-bold"
                    : "hover:bg-[#1E2833]/50 text-[#C8D4E0]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{
                      backgroundColor: p.role === "primary" ? "#3DD68C" : "#E5484D",
                    }}
                  />
                  <span>{p.name}</span>
                </div>
                <span className="text-[10px] text-[#6B7A8C] uppercase">{p.role}</span>
              </button>
            );
          })}
        </div>

        {/* Selected Satellite Telemetry Details */}
        {selectedTrack && (
          <div className="mt-3 pt-2 border-t border-[#1E2833] text-[11px] text-[#6B7A8C] flex flex-col gap-2">
            <div>
              NORAD ID: <span className="text-[#C8D4E0] font-bold">{selectedTrack.id}</span>
            </div>
            <div>
              POINTS LOADED: <span className="text-[#C8D4E0] font-bold">{selectedTrack.coords.length}</span>
            </div>
            <button
              onClick={() => setSelectedTrack(null)}
              className="mt-1 w-full py-1 bg-[#1E2833] hover:bg-[#283545] text-[#C8D4E0] rounded text-[10px] uppercase font-bold transition-all"
            >
              Show All Orbits
            </button>
          </div>
        )}
      </div>

      <Globe
        ref={globeRef}
        width={dimensions.width}
        height={dimensions.height}
        globeImageUrl="https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg"
        backgroundColor="rgba(7,10,15,1)"
        // Orbit Paths
        pathsData={selectedTrack ? [selectedTrack] : paths}
        pathPoints="coords"
        pathPointLat={(d) => d[0]}
        pathPointLng={(d) => d[1]}
        pathPointAlt={(d) => d[2] / 6371}
        pathColor={(d) => (d.role === "primary" ? "#3DD68C" : "#E5484D")}
        pathStroke={3}
        pathLabel={(d) => `<div style="background:#0E141C; padding:4px 8px; border-radius:4px; font-family:monospace; color:#C8D4E0; font-size:12px; border:1px solid #1E2833"><b>${d.name}</b> (${d.role.toUpperCase()})</div>`}
        onPathClick={(path) => setSelectedTrack(path)}
        // Glowing HTML Pulsing Beacon Markers at current scrubber index
        htmlElementsData={currentPositions}
        htmlLat="lat"
        htmlLng="lng"
        htmlAltitude="alt"
        htmlElement={(d) => {
          const el = document.createElement("div");
          const color = d.role === "primary" ? "#3DD68C" : "#E5484D";
          el.innerHTML = `
            <div style="position: relative; display: flex; align-items: center; justify-content: center; transform: translate(-50%, -50%); pointer-events: none;">
              <div style="position: absolute; width: 28px; height: 28px; border-radius: 50%; background-color: ${color}; opacity: 0.5; animation: pulse 1.2s ease-in-out infinite;"></div>
              <div style="width: 14px; height: 14px; border-radius: 50%; background-color: ${color}; border: 2px solid #FFFFFF; box-shadow: 0 0 14px ${color}; z-index: 2;"></div>
              <div style="position: absolute; top: -26px; white-space: nowrap; background: #0E141C; color: #C8D4E0; border: 1px solid #1E2833; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 11px; font-weight: bold; box-shadow: 0 4px 10px rgba(0,0,0,0.5);">
                <span style="color: ${color};">●</span> ${d.name}
              </div>
            </div>
          `;
          return el;
        }}
        // Expanding 3D Radar Rings
        ringsData={currentPositions}
        ringLat="lat"
        ringLng="lng"
        ringAltitude="alt"
        ringColor={(d) => (d.role === "primary" ? "#3DD68C" : "#E5484D")}
        ringMaxRadius={8}
        ringPropagationSpeed={4}
        ringRepeatPeriod={700}
        // Debris Cloud Backdrop
        pointsData={debris}
        pointLat="lat"
        pointLng="lon"
        pointAltitude={(d) => d.alt_km / 6371}
        pointColor={() => "rgba(107, 122, 140, 0.6)"}
        pointRadius={0.2}
      />
    </div>
  );
}







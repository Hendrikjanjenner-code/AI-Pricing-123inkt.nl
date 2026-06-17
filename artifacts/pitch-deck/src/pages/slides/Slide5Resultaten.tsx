export default function Slide5Resultaten() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow */}
      <div className="absolute" style={{
        width: "50vw", height: "50vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)",
        bottom: "-15vw", left: "-10vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>04 — Resultaten</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "9vh 5vw 8vh 5vw" }}>

        <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Gemeten impact op marge en efficientie
        </h2>

        {/* Big stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "2vw", marginBottom: "4vh" }}>

          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "8.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>+4.2<span style={{ fontSize: "4vw" }}>%</span></div>
            <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "1.2vh", fontWeight: 500 }}>Brutomarge uplift</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", opacity: 0.7 }}>AI vs. handmatige prijzen</div>
          </div>

          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "8.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #7C6BF0, #4F7FFF)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>-70<span style={{ fontSize: "4vw" }}>%</span></div>
            <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "1.2vh", fontWeight: 500 }}>Minder handmatig werk</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", opacity: 0.7 }}>Uren per dag per analist</div>
          </div>

          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "8.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>87<span style={{ fontSize: "4vw" }}>%</span></div>
            <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "1.2vh", fontWeight: 500 }}>Goedkeuringspercentage</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", opacity: 0.7 }}>Analisten vertrouwen AI</div>
          </div>

          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: "8.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #7C6BF0, #4F7FFF)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>&lt;1<span style={{ fontSize: "4vw" }}>h</span></div>
            <div style={{ fontSize: "1vw", color: "#8892B0", marginTop: "1.2vh", fontWeight: 500 }}>Time-to-market</div>
            <div style={{ fontSize: "0.85vw", color: "#8892B0", opacity: 0.7 }}>Van beslissing tot live prijs</div>
          </div>
        </div>

        {/* Two detail cards */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2vw" }}>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.5vh 2vw" }}>
            <div style={{ fontSize: "1.1vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.8vh" }}>A/B-test: AI vs. Controle</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Marge-uplift (AI-groep)</span>
                <span style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF" }}>+3.8%</span>
              </div>
              <div style={{ height: "0.6vh", background: "rgba(79,127,255,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                <div style={{ width: "76%", height: "100%", background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", borderRadius: "1px" }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Conversie-uplift</span>
                <span style={{ fontSize: "1vw", fontWeight: 700, color: "#7C6BF0" }}>+1.2%</span>
              </div>
              <div style={{ height: "0.6vh", background: "rgba(124,107,240,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                <div style={{ width: "42%", height: "100%", background: "linear-gradient(90deg, #7C6BF0, #4F7FFF)", borderRadius: "1px" }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Statistische zekerheid</span>
                <span style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF" }}>94%</span>
              </div>
              <div style={{ height: "0.6vh", background: "rgba(79,127,255,0.15)", borderRadius: "1px", overflow: "hidden" }}>
                <div style={{ width: "94%", height: "100%", background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", borderRadius: "1px" }} />
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2.5vh 2vw" }}>
            <div style={{ fontSize: "1.1vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.8vh" }}>Veiligheidssysteem: nul fouten</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5vh" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "0.8vw", height: "0.8vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Prijsvloer: koopprijs x 1,01 — altijd gewaarborgd</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "0.8vw", height: "0.8vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Max. 5% prijswijziging per dag — geen schokken</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "0.8vw", height: "0.8vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Lage confidence (&lt;40%) wordt gemarkeerd als waarschuwing</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "0.8vw", height: "0.8vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Out-of-stock blokkeert aanbeveling (uitzondering: clearance)</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "0.8vw", height: "0.8vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Volledige audittrail — elke beslissing herleidbaar</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

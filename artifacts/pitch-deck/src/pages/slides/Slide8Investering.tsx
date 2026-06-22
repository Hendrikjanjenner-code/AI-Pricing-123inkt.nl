export default function Slide8Investering() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow orbs */}
      <div className="absolute" style={{
        width: "55vw", height: "55vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(79,127,255,0.14) 0%, transparent 70%)",
        top: "-20vw", right: "-15vw"
      }} />
      <div className="absolute" style={{
        width: "35vw", height: "35vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)",
        bottom: "-10vw", left: "-5vw"
      }} />

      {/* Slide label */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>07 — Investering en Impact</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "10vh 5vw 8vh 5vw", gap: "5vw" }}>

        {/* Left: financiele impact */}
        <div style={{ flex: "0 0 45vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>

          <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "4.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            Investering versus impact
          </h2>

          {/* ROI cards */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2vw", marginBottom: "4vh" }}>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "2.5vh 2vw", textAlign: "center" }}>
              <div style={{ fontSize: "4.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>EUR 2,1M</div>
              <div style={{ fontSize: "0.95vw", color: "#8892B0", marginTop: "1vh", fontWeight: 500 }}>Geschatte jaarlijkse margewinst</div>
              <div style={{ fontSize: "0.8vw", color: "#8892B0", opacity: 0.7, marginTop: "0.4vh" }}>Bij volledige uitrol 26.000+ SKU's</div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "0.8vw", padding: "2.5vh 2vw", textAlign: "center" }}>
              <div style={{ fontSize: "4.5vw", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #7C6BF0, #4F7FFF)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>&lt;6 mnd</div>
              <div style={{ fontSize: "0.95vw", color: "#8892B0", marginTop: "1vh", fontWeight: 500 }}>Terugverdientijd</div>
              <div style={{ fontSize: "0.8vw", color: "#8892B0", opacity: 0.7, marginTop: "0.4vh" }}>Op basis van pilotresultaten</div>
            </div>
          </div>

          {/* Investment breakdown */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2.5vh 2vw" }}>
            <div style={{ fontSize: "1.05vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "2vh" }}>Wat we vragen</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.5vh" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Productiedeployment goedkeuren</span>
                <span style={{ fontSize: "0.9vw", fontWeight: 600, color: "#4F7FFF" }}>Besluit</span>
              </div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Budget Q3 uitbreiding</span>
                <span style={{ fontSize: "0.9vw", fontWeight: 600, color: "#7C6BF0" }}>EUR 85K</span>
              </div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Datakoppeling live-omgeving</span>
                <span style={{ fontSize: "0.9vw", fontWeight: 600, color: "#4F7FFF" }}>IT-prioriteit</span>
              </div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>2 FTE pricing analisten training</span>
                <span style={{ fontSize: "0.9vw", fontWeight: 600, color: "#7C6BF0" }}>2 weken</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: call to action */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "flex-start" }}>

          <div style={{
            background: "linear-gradient(135deg, rgba(79,127,255,0.12), rgba(124,107,240,0.12))",
            border: "1px solid rgba(79,127,255,0.3)",
            borderRadius: "1vw",
            padding: "4vh 2.5vw",
            marginBottom: "3vh",
            width: "100%"
          }}>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "2.5vh" }}>Platform vandaag beschikbaar</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.8vh" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "1.4vw", height: "1.4vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <span style={{ fontSize: "0.95vw", color: "#F0F4FF", fontWeight: 500 }}>Volledig functionele demo beschikbaar</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "1.4vw", height: "1.4vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <span style={{ fontSize: "0.95vw", color: "#F0F4FF", fontWeight: 500 }}>Alle 10 modules operationeel</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "1.4vw", height: "1.4vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <span style={{ fontSize: "0.95vw", color: "#F0F4FF", fontWeight: 500 }}>Interne prijspublicatie gevalideerd</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "1vw" }}>
                <div style={{ width: "1.4vw", height: "1.4vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <span style={{ fontSize: "0.95vw", color: "#F0F4FF", fontWeight: 500 }}>Veiligheidsregels en audittrail actief</span>
              </div>
            </div>
          </div>

          {/* Logo / closer */}
          <div style={{ width: "100%", textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.8vw", marginBottom: "1.5vh" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="60%" height="60%" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/>
                </svg>
              </div>
              <span style={{ fontSize: "1.6vw", fontWeight: 800, color: "#F0F4FF" }}>AI Pricing Engine</span>
            </div>
            <div style={{ fontSize: "0.95vw", color: "#8892B0" }}>123inkt — Pricing Team</div>
          </div>
        </div>
      </div>
    </div>
  );
}

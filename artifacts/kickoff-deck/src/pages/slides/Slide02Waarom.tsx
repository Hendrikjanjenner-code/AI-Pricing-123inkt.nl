export default function Slide02Waarom() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-12vw", right: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>01 — Waarom dit project?</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 7vh 5vw", gap: "4vw" }}>

        {/* Left: huidige situatie */}
        <div style={{ flex: "0 0 44vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            Vandaag werken we met losse tools en losse kennis
          </h2>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.5vh", marginBottom: "3vh" }}>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", padding: "1.5vh 1.6vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "0.4vw", height: "3.5vh", background: "#4F7FFF", borderRadius: "1px", flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: "1.05vw", fontWeight: 600, color: "#F0F4FF" }}>PriceShape, Excel, handmatige concurrentiebeoordelingen</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", marginTop: "0.3vh" }}>Losse systemen zonder gedeeld datamodel</div>
              </div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.7vw", padding: "1.5vh 1.6vw", display: "flex", alignItems: "center", gap: "1.2vw" }}>
              <div style={{ width: "0.4vw", height: "3.5vh", background: "#7C6BF0", borderRadius: "1px", flexShrink: 0 }} />
              <div>
                <div style={{ fontSize: "1.05vw", fontWeight: 600, color: "#F0F4FF" }}>Losse rapportages, veel kennis in hoofden</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", marginTop: "0.3vh" }}>Inzichten zijn niet schaalbaar of auditeerbaar</div>
              </div>
            </div>
          </div>

          <div style={{ padding: "1.8vh 1.8vw", background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw" }}>
            <div style={{ fontSize: "0.9vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "0.8vh", letterSpacing: "0.05em", textTransform: "uppercase" }}>Resultaat</div>
            <div style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.6 }}>Veel analyses kosten tijd &#8212; terwijl concurrenten in uren reageren en externe factoren moeilijk te voorspellen zijn.</div>
          </div>
        </div>

        {/* Right: uitdagingen */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: "1.5vh" }}>
          <div style={{ fontSize: "1.1vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.5vh" }}>Concrete uitdagingen</div>

          <div style={{ background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.7vw", padding: "1.5vh 1.5vw", display: "flex", alignItems: "flex-start", gap: "0.8vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
            <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>Niet iedere concurrent is relevant &#8212; hoe bepalen we dat?</span>
          </div>
          <div style={{ background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.7vw", padding: "1.5vh 1.5vw", display: "flex", alignItems: "flex-start", gap: "0.8vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
            <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>Huismerkpotentie wordt niet altijd zichtbaar gemaakt</span>
          </div>
          <div style={{ background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.7vw", padding: "1.5vh 1.5vw", display: "flex", alignItems: "flex-start", gap: "0.8vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
            <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>Prijsgaps zijn lastig structureel te beheren</span>
          </div>
          <div style={{ background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.7vw", padding: "1.5vh 1.5vw", display: "flex", alignItems: "flex-start", gap: "0.8vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.6vh", flexShrink: 0 }} />
            <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>Externe factoren zijn moeilijk te voorspellen of signaleren</span>
          </div>
          <div style={{ background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.7vw", padding: "1.5vh 1.5vw", display: "flex", alignItems: "flex-start", gap: "0.8vw" }}>
            <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.6vh", flexShrink: 0 }} />
            <span style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>Veel analyses kosten tijd die beter aan beslissingen besteed kan worden</span>
          </div>
        </div>
      </div>
    </div>
  );
}

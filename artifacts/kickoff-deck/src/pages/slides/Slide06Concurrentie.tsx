export default function Slide06Concurrentie() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "45vw", height: "45vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.1) 0%, transparent 70%)", top: "-15vw", right: "-10vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>05 — Concurrentie Intelligence</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 7vh 5vw", gap: "4vw" }}>

        {/* Left: voorbeeld */}
        <div style={{ flex: "0 0 44vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "1.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            Niet iedere concurrent telt even zwaar
          </h2>
          <p style={{ fontSize: "1.05vw", color: "#8892B0", lineHeight: 1.6, marginBottom: "3vh" }}>
            Blind de laagste prijs volgen kost marge. AI bepaalt of een prijsbeweging van een concurrent relevant en betrouwbaar is.
          </p>

          {/* Voorbeeld */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.9vw", padding: "2.5vh 2vw", marginBottom: "2.5vh" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Praktijkscenario</div>
            <div style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600, marginBottom: "0.8vh" }}>123inkt: toner EUR 250 &#8212; concurrent verlaagt naar EUR 199</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.8vh" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6vw" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#8892B0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Is dit een tijdelijke actie?</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6vw" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#8892B0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Heeft de concurrent voorraad?</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6vw" }}>
                <div style={{ width: "0.4vw", height: "0.4vw", borderRadius: "50%", background: "#8892B0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Is dit een stuntprijs of structurele aanpassing?</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: AI bepaalt */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: "1.5vh" }}>
          <div style={{ fontSize: "1.05vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.5vh" }}>AI beoordeelt automatisch</div>

          <div style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.8vw", padding: "2vh 1.8vw" }}>
            <div style={{ fontSize: "0.85vw", fontWeight: 700, color: "#4F7FFF", marginBottom: "0.8vh" }}>Concurrentierelevantie</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.5 }}>Welk marktaandeel, welke overlappende SKU's, welke klantgroep?</div>
          </div>
          <div style={{ background: "rgba(124,107,240,0.1)", border: "1px solid rgba(124,107,240,0.3)", borderRadius: "0.8vw", padding: "2vh 1.8vw" }}>
            <div style={{ fontSize: "0.85vw", fontWeight: 700, color: "#7C6BF0", marginBottom: "0.8vh" }}>Prijsimpact</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.5 }}>Wat is het verwachte volume-effect als we niet reageren?</div>
          </div>
          <div style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.8vw", padding: "2vh 1.8vw" }}>
            <div style={{ fontSize: "0.85vw", fontWeight: 700, color: "#4F7FFF", marginBottom: "0.8vh" }}>Betrouwbaarheid</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.5 }}>Is de concurrent winstgevend genoeg om dit vol te houden?</div>
          </div>

          <div style={{ padding: "1.5vh 1.5vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.7vw" }}>
            <span style={{ fontSize: "0.9vw", color: "#F0F4FF", fontWeight: 500 }}>Resultaat: </span>
            <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>gerichte reactie in plaats van blinde prijsvolging</span>
          </div>
        </div>
      </div>
    </div>
  );
}

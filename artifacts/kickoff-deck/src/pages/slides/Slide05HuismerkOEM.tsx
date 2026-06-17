export default function Slide05HuismerkOEM() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.12) 0%, transparent 70%)", bottom: "-12vw", left: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>04 — Huismerk vs OEM Intelligence</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 7vh 5vw", gap: "4vw" }}>

        {/* Left */}
        <div style={{ flex: "0 0 42vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.6vw", background: "rgba(124,107,240,0.12)", border: "1px solid rgba(124,107,240,0.3)", borderRadius: "2vw", padding: "0.4vh 1.2vw", marginBottom: "2vh" }}>
            <span style={{ fontSize: "0.8vw", fontWeight: 700, color: "#7C6BF0", letterSpacing: "0.08em", textTransform: "uppercase" }}>Nieuw module</span>
          </div>
          <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            PrijsGap Intelligence
          </h2>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.3vh", marginBottom: "3vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Huidige OEM prijs</span>
              <span style={{ fontSize: "0.9vw", fontWeight: 700, color: "#4F7FFF" }}>Per SKU bepaald</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Huidige huismerk prijs</span>
              <span style={{ fontSize: "0.9vw", fontWeight: 700, color: "#7C6BF0" }}>Per SKU bepaald</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Optimale / maximale prijsgap</span>
              <span style={{ fontSize: "0.9vw", fontWeight: 700, color: "#4F7FFF" }}>AI berekend</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Break-even punt + substitutiepotentie</span>
              <span style={{ fontSize: "0.9vw", fontWeight: 700, color: "#7C6BF0" }}>AI berekend</span>
            </div>
          </div>
        </div>

        {/* Right */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.9vw", padding: "3vh 2.5vw", marginBottom: "2.5vh" }}>
            <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>De kernvraag voor dit module</div>
            <div style={{ fontSize: "1.2vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1.4, marginBottom: "1.5vh" }}>
              Wanneer wordt een OEM-klant bereid om over te stappen naar huismerk?
            </div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.6 }}>
              Dit is exact het soort analyse waar AI zeer sterk in is. Per SKU, per klantsegment, per prijsgap &#8212; automatisch en dagelijks bijgewerkt.
            </div>
          </div>

          <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.1), rgba(124,107,240,0.1))", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.9vw", padding: "2vh 2vw" }}>
            <div style={{ fontSize: "0.85vw", color: "#7C6BF0", fontWeight: 700, marginBottom: "0.8vh" }}>Resultaat</div>
            <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.6 }}>
              Structureel inzicht in welke OEM-klanten overstapkandidaten zijn en bij welke prijsgap de conversie naar huismerk maximaliseert.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

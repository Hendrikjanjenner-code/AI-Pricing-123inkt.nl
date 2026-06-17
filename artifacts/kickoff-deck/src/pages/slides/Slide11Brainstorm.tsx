export default function Slide11Brainstorm() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-12vw", right: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>10 — Brainstormsessie</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "8.5vh 5vw 6.5vh 5vw" }}>
        <h2 style={{ fontSize: "3.2vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Input van het team per discipline
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: "1.2vw" }}>

          <div style={{ background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.8vw", padding: "2vh 1.4vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Pricing Team</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke analyses kosten vandaag de meeste tijd?</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.15)" }} />
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke pricingbeslissingen zijn het lastigst?</div>
            </div>
          </div>

          <div style={{ background: "rgba(124,107,240,0.08)", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "0.8vw", padding: "2vh 1.4vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1.5vh" }}>CATMAN</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke categorieen hebben de grootste kansen?</div>
              <div style={{ height: "1px", background: "rgba(124,107,240,0.15)" }} />
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Waar zit ongenutte huismerkpotentie?</div>
            </div>
          </div>

          <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.4vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Marketing</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke producten trekken het meeste verkeer?</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.15)" }} />
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke producten converteren structureel slecht?</div>
            </div>
          </div>

          <div style={{ background: "rgba(124,107,240,0.08)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.8vw", padding: "2vh 1.4vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Inkoop</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke leveranciers zijn risicovol?</div>
              <div style={{ height: "1px", background: "rgba(124,107,240,0.15)" }} />
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke kostprijsontwikkelingen zien jullie aankomen?</div>
            </div>
          </div>

          <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 1.4vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Management</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke inzichten missen we vandaag?</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.15)" }} />
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Welke KPI's moeten zichtbaarder worden?</div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: "2.5vh", padding: "1.6vh 2vw", background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", display: "flex", alignItems: "center", gap: "1vw" }}>
          <div style={{ width: "0.3vw", height: "3vh", background: "linear-gradient(180deg, #4F7FFF, #7C6BF0)", borderRadius: "1px", flexShrink: 0 }} />
          <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Doel van de sessie: <span style={{ color: "#F0F4FF", fontWeight: 500 }}>concrete prioriteiten vaststellen voor scope, data en governance in de eerste fase.</span></span>
        </div>
      </div>
    </div>
  );
}

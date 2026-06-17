export default function Slide04Visie() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "50vw", height: "50vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.12) 0%, transparent 70%)", top: "-18vw", right: "-10vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>03 — De Visie voor 123inkt</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col justify-center" style={{ padding: "9vh 5vw 7vh 5vw" }}>

        {/* Kernvraag */}
        <div style={{ textAlign: "center", marginBottom: "4vh" }}>
          <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1.5vh" }}>De kernvraag</div>
          <h2 style={{ fontSize: "3.2vw", fontWeight: 800, color: "#F0F4FF", lineHeight: 1.15, letterSpacing: "-0.02em", textWrap: "balance", margin: 0 }}>
            Hoe gebruiken we A-merken om maximaal<br />
            <span style={{ background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>winstgevende huismerkverkoop</span> te realiseren?
          </h2>
        </div>

        {/* Two columns: A-merk vs Huismerk */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2.5vw", marginBottom: "3vh" }}>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.9vw", padding: "2.5vh 2vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>A-merken zorgen voor</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Zoekverkeer</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Vertrouwen bij klanten</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Conversie en bereik</span>
              </div>
            </div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "0.9vw", padding: "2.5vh 2vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Huismerken zorgen voor</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Hogere bruto marge</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Betere winstgevendheid</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "1vw", color: "#F0F4FF", fontWeight: 600 }}>Meer commerciele ruimte</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom insight */}
        <div style={{ background: "linear-gradient(90deg, rgba(79,127,255,0.1), rgba(124,107,240,0.1))", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "1.8vh 2vw", textAlign: "center" }}>
          <span style={{ fontSize: "1.1vw", color: "#F0F4FF", fontWeight: 600 }}>Het model moet beide combineren &#8212; </span>
          <span style={{ fontSize: "1.1vw", color: "#8892B0" }}>AI bepaalt per SKU wanneer A-merk traffic omgezet kan worden naar winstgevende huismerkverkoop.</span>
        </div>
      </div>
    </div>
  );
}

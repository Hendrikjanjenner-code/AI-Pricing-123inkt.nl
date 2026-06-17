export default function Slide12Eindresultaat() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid */}
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.06) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />

      {/* Glow orbs */}
      <div className="absolute" style={{ width: "60vw", height: "60vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.14) 0%, transparent 70%)", top: "-25vw", right: "-20vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-15vw", left: "-8vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>11 — Het gewenste eindresultaat</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.4vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 7vh 5vw", gap: "5vw" }}>

        {/* Left: daily questions */}
        <div style={{ flex: "0 0 46vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.4vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "1vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            Dagelijks antwoord op de<br />
            <span style={{ background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>juiste vragen</span>
          </h2>
          <p style={{ fontSize: "1vw", color: "#8892B0", marginBottom: "3vh", lineHeight: 1.6 }}>Een platform dat automatisch inzicht geeft op zeven kernvragen.</p>

          <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.7vh", flexShrink: 0 }} />
              <span style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>Wat moeten we vandaag aanpassen?</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.7vh", flexShrink: 0 }} />
              <span style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>Waarom moeten we dit aanpassen?</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.7vh", flexShrink: 0 }} />
              <span style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>Wat is het verwachte effect op marge?</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#7C6BF0", marginTop: "0.7vh", flexShrink: 0 }} />
              <span style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>Hoe beinvloedt dit traffic en conversie?</span>
            </div>
            <div style={{ display: "flex", alignItems: "flex-start", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#4F7FFF", marginTop: "0.7vh", flexShrink: 0 }} />
              <span style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>Hoe beinvloedt dit huismerk en concurrentiepositie?</span>
            </div>
          </div>
        </div>

        {/* Right: de belofte */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>

          {/* Big promise */}
          <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.15), rgba(124,107,240,0.15))", border: "1px solid rgba(79,127,255,0.4)", borderRadius: "1vw", padding: "4vh 2.5vw", marginBottom: "2.5vh" }}>
            <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>De belofte</div>
            <div style={{ fontSize: "1.5vw", fontWeight: 800, color: "#F0F4FF", lineHeight: 1.35, marginBottom: "1.5vh" }}>
              Niet meer reageren op de markt.
            </div>
            <div style={{ fontSize: "1.3vw", fontWeight: 700, lineHeight: 1.35, background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              De markt proactief begrijpen en benutten.
            </div>
          </div>

          {/* Logo closer */}
          <div style={{ textAlign: "center" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.8vw", marginBottom: "0.8vh" }}>
              <div style={{ width: "2.8vw", height: "2.8vw", borderRadius: "0.6vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="60%" height="60%" viewBox="0 0 16 16" fill="none"><path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/></svg>
              </div>
              <span style={{ fontSize: "1.4vw", fontWeight: 800, color: "#F0F4FF" }}>Commercial Intelligence</span>
            </div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0" }}>123inkt &#8212; Pricing &amp; Intelligence Team</div>
          </div>
        </div>
      </div>
    </div>
  );
}

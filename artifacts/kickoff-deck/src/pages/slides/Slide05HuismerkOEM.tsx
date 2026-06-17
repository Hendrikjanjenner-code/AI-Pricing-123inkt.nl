export default function Slide05HuismerkOEM() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-12vw", left: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>04 — Substitutiepotentieel &amp; Huismerk Intelligence</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 6.5vh 5vw", gap: "3.5vw" }}>

        {/* Left: definitie + twee typen */}
        <div style={{ flex: "0 0 46vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.2vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "1.2vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            Substitutiepotentieel als kernconcept
          </h2>
          <p style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.6, marginBottom: "2.5vh" }}>
            De mate waarin een klant uw product inruilt voor een alternatief wanneer u uw prijs verandert. Bepalend voor uw prijselasticiteit en margeruimte.
          </p>

          {/* Twee typen */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5vw", marginBottom: "2.5vh" }}>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
              <div style={{ fontSize: "0.75vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1vh" }}>Klantverloop</div>
              <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.8vh" }}>Naar een concurrent</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.55 }}>
                <span style={{ color: "#4F7FFF", fontWeight: 600 }}>Hoog:</span> commodity, weinig margeruimte
              </div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.55, marginTop: "0.4vh" }}>
                <span style={{ color: "#4F7FFF", fontWeight: 600 }}>Laag:</span> sterk merk, aanzienlijke prijsruimte
              </div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.3)", borderRadius: "0.8vw", padding: "2vh 1.6vw" }}>
              <div style={{ fontSize: "0.75vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1vh" }}>Interne substitutie</div>
              <div style={{ fontSize: "0.95vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.8vh" }}>OEM &#8594; Huismerk</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.55 }}>
                Klant kiest bij OEM-prijsstijging een goedkoper alternatief uit hetzelfde portfolio &#8212; <span style={{ color: "#7C6BF0", fontWeight: 600 }}>precies de kans voor 123inkt</span>
              </div>
            </div>
          </div>

          {/* 4 factoren */}
          <div style={{ background: "rgba(79,127,255,0.07)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "1.8vh 1.8vw" }}>
            <div style={{ fontSize: "0.78vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1vh" }}>4 bepalende factoren</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8vh 2vw" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5vw" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.85vw", color: "#8892B0" }}>Beschikbaarheid van alternatieven</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5vw" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.85vw", color: "#8892B0" }}>Overschakelkosten (switching costs)</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5vw" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.85vw", color: "#8892B0" }}>Unieke waarde van het product</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5vw" }}>
                <div style={{ width: "0.35vw", height: "0.35vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.85vw", color: "#8892B0" }}>Prijs-kwaliteitsverhouding</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: PrijsGap toepassing */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: "0.6vw", background: "rgba(124,107,240,0.12)", border: "1px solid rgba(124,107,240,0.3)", borderRadius: "2vw", padding: "0.4vh 1.2vw", marginBottom: "1.8vh" }}>
            <span style={{ fontSize: "0.8vw", fontWeight: 700, color: "#7C6BF0", letterSpacing: "0.08em", textTransform: "uppercase" }}>AI Toepassing</span>
          </div>
          <div style={{ fontSize: "1.3vw", fontWeight: 800, color: "#F0F4FF", lineHeight: 1.3, marginBottom: "2.5vh" }}>
            PrijsGap Intelligence
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.2vh", marginBottom: "2.5vh" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.88vw", color: "#8892B0" }}>Substitutiepotentie per SKU</span>
              <span style={{ fontSize: "0.88vw", fontWeight: 700, color: "#4F7FFF" }}>AI berekend</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.88vw", color: "#8892B0" }}>Optimale / maximale prijsgap</span>
              <span style={{ fontSize: "0.88vw", fontWeight: 700, color: "#7C6BF0" }}>AI berekend</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.88vw", color: "#8892B0" }}>Break-even punt OEM vs. huismerk</span>
              <span style={{ fontSize: "0.88vw", fontWeight: 700, color: "#4F7FFF" }}>AI berekend</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.15)", borderRadius: "0.6vw" }}>
              <span style={{ fontSize: "0.88vw", color: "#8892B0" }}>Switching costs per klantsegment</span>
              <span style={{ fontSize: "0.88vw", fontWeight: 700, color: "#7C6BF0" }}>AI berekend</span>
            </div>
          </div>

          <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.12), rgba(124,107,240,0.12))", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.8vw", padding: "2vh 1.8vw" }}>
            <div style={{ fontSize: "0.8vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "0.7vh" }}>Doel</div>
            <div style={{ fontSize: "0.92vw", color: "#8892B0", lineHeight: 1.55 }}>
              Per OEM-klant weten: bij welke prijsgap zijn ze bereid over te stappen naar huismerk, zonder het OEM-vertrouwen en de bijbehorende traffic te verliezen.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

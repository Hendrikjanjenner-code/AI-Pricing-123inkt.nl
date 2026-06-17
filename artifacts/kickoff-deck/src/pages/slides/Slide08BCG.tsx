export default function Slide08BCG() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "45vw", height: "45vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.1) 0%, transparent 70%)", top: "-15vw", right: "-10vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>07 — BCG Intelligence</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "8.5vh 5vw 7vh 5vw" }}>

        <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "4vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Intern en extern BCG &#8212; automatisch bijgehouden
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3vw", marginBottom: "3vh" }}>

          {/* Intern BCG */}
          <div>
            <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Interne BCG per SKU</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.2vw" }}>
              <div style={{ background: "rgba(79,127,255,0.12)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.7vw", padding: "1.8vh 1.4vw" }}>
                <div style={{ fontSize: "1.1vw", fontWeight: 800, color: "#4F7FFF", marginBottom: "0.5vh" }}>Stars</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Hoog aandeel, hoge groei &#8212; investeren en beschermen</div>
              </div>
              <div style={{ background: "rgba(124,107,240,0.12)", border: "1px solid rgba(124,107,240,0.3)", borderRadius: "0.7vw", padding: "1.8vh 1.4vw" }}>
                <div style={{ fontSize: "1.1vw", fontWeight: 800, color: "#7C6BF0", marginBottom: "0.5vh" }}>Cash Cows</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Hoog aandeel, lage groei &#8212; marge maximaliseren</div>
              </div>
              <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.7vw", padding: "1.8vh 1.4vw" }}>
                <div style={{ fontSize: "1.1vw", fontWeight: 800, color: "#4F7FFF", marginBottom: "0.5vh" }}>Question Marks</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Laag aandeel, hoge groei &#8212; kansen beoordelen</div>
              </div>
              <div style={{ background: "rgba(124,107,240,0.08)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.7vw", padding: "1.8vh 1.4vw" }}>
                <div style={{ fontSize: "1.1vw", fontWeight: 800, color: "#7C6BF0", marginBottom: "0.5vh" }}>Dogs</div>
                <div style={{ fontSize: "0.85vw", color: "#8892B0", lineHeight: 1.5 }}>Laag aandeel, lage groei &#8212; afbouwen of afstoten</div>
              </div>
            </div>
          </div>

          {/* Extern BCG */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: "0.85vw", color: "#7C6BF0", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Externe BCG per markt</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh", marginBottom: "2.5vh" }}>
              <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", padding: "1.3vh 1.4vw", display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Marktvraag en groeipotentie</span>
              </div>
              <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.7vw", padding: "1.3vh 1.4vw", display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Concurrentiedruk per categorie</span>
              </div>
              <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", padding: "1.3vh 1.4vw", display: "flex", alignItems: "center", gap: "0.8vw" }}>
                <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
                <span style={{ fontSize: "0.9vw", color: "#8892B0" }}>Marktpositie vs. concurrenten</span>
              </div>
            </div>

            <div style={{ background: "rgba(79,127,255,0.08)", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.7vw", padding: "1.8vh 1.5vw" }}>
              <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "0.8vh" }}>Automatische signalering</div>
              <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.55 }}>Wanneer een SKU, categorie of markt van kwadrant verschuift &#8212; direct zichtbaar in het dashboard.</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Slide07Traffic() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "35vw", height: "35vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-10vw", right: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>05 — Traffic &amp; Demand Intelligence</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "8.5vh 5vw 7vh 5vw" }}>

        <h2 style={{ fontSize: "3.6vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "4vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          Per SKU begrijpen we traffic, conversie en vraag
        </h2>

        {/* Drie scores */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "2vw", marginBottom: "3.5vh" }}>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.9vw", padding: "2.5vh 1.8vw" }}>
            <div style={{ fontSize: "3.5vw", fontWeight: 900, color: "#4F7FFF", lineHeight: 1, marginBottom: "1.2vh" }}>TDS</div>
            <div style={{ fontSize: "1.05vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.8vh" }}>Traffic Driver Score</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.55 }}>Welke producten trekken bezoekers naar de site en zorgen voor zoekverkeer?</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "0.9vw", padding: "2.5vh 1.8vw" }}>
            <div style={{ fontSize: "3.5vw", fontWeight: 900, color: "#7C6BF0", lineHeight: 1, marginBottom: "1.2vh" }}>BBS</div>
            <div style={{ fontSize: "1.05vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.8vh" }}>Basket Builder Score</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.55 }}>Welke producten vullen winkelmandjes en zorgen voor herhaalaankopen?</div>
          </div>

          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.9vw", padding: "2.5vh 1.8vw" }}>
            <div style={{ fontSize: "3.5vw", fontWeight: 900, color: "#4F7FFF", lineHeight: 1, marginBottom: "1.2vh" }}>EPS</div>
            <div style={{ fontSize: "1.05vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.8vh" }}>Entry Product Score</div>
            <div style={{ fontSize: "0.9vw", color: "#8892B0", lineHeight: 1.55 }}>Welke producten zijn de eerste aankoop die leiden tot klantloyaliteit?</div>
          </div>
        </div>

        {/* Insights */}
        <div style={{ background: "linear-gradient(90deg, rgba(79,127,255,0.1), rgba(124,107,240,0.08))", border: "1px solid rgba(79,127,255,0.2)", borderRadius: "0.8vw", padding: "2vh 2.5vw" }}>
          <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "1.2vh", letterSpacing: "0.05em", textTransform: "uppercase" }}>Nieuw inzicht per SKU</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "2vw" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.4vh" }}>Traffic</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Welke SKU's trekken bezoek?</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.4vh" }}>Conversie</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Welke SKU's converteren slecht?</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.4vh" }}>Vraag</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Wat is het zoekvolume en de marktpotentie?</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1vw", fontWeight: 600, color: "#F0F4FF", marginBottom: "0.4vh" }}>Loyaliteit</div>
              <div style={{ fontSize: "0.85vw", color: "#8892B0" }}>Welke producten zorgen voor herhaalaankoop?</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Slide03AIWelNiet() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "35vw", height: "35vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.1) 0%, transparent 70%)", top: "-10vw", left: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>02 — Wat AI wel en niet kan</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex flex-col" style={{ padding: "8.5vh 5vw 7vh 5vw" }}>
        <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3.5vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          AI is een krachtig adviesinstrument &#8212; geen orakel
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2.5vw", marginBottom: "3vh" }}>

          {/* AI kan WEL */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.3)", borderRadius: "0.9vw", padding: "2.5vh 2vw" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", marginBottom: "2vh" }}>
              <div style={{ width: "1.5vw", height: "1.5vw", borderRadius: "50%", background: "rgba(79,127,255,0.2)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </div>
              <span style={{ fontSize: "1.1vw", fontWeight: 700, color: "#4F7FFF" }}>AI kan wel</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Miljoenen datapunten analyseren en patronen herkennen</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Prijselasticiteit berekenen en concurrentie analyseren</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Promoties evalueren en traffic drivers herkennen</div>
              <div style={{ height: "1px", background: "rgba(79,127,255,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Forecasting ondersteunen met historische signalen</div>
            </div>
          </div>

          {/* AI kan NIET */}
          <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.2)", borderRadius: "0.9vw", padding: "2.5vh 2vw" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", marginBottom: "2vh" }}>
              <div style={{ width: "1.5vw", height: "1.5vw", borderRadius: "50%", background: "rgba(124,107,240,0.2)", border: "1px solid #7C6BF0", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <svg width="55%" height="55%" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M9 3l-6 6" stroke="#7C6BF0" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </div>
              <span style={{ fontSize: "1.1vw", fontWeight: 700, color: "#7C6BF0" }}>AI kan niet</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "1vh" }}>
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Een oorlog, COVID of leveranciersbeslissingen voorspellen</div>
              <div style={{ height: "1px", background: "rgba(124,107,240,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Politieke besluiten of marktschokken voorspellen</div>
              <div style={{ height: "1px", background: "rgba(124,107,240,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Vertrouwens- of relatiefactoren inschatten</div>
              <div style={{ height: "1px", background: "rgba(124,107,240,0.1)" }} />
              <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.5 }}>Menselijk oordeel en domeinexpertise vervangen</div>
            </div>
          </div>
        </div>

        {/* COVID voorbeeld */}
        <div style={{ background: "linear-gradient(90deg, rgba(79,127,255,0.1), rgba(124,107,240,0.08))", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "1.8vh 2vw", display: "flex", alignItems: "center", gap: "1.5vw" }}>
          <div style={{ width: "0.3vw", height: "4vh", background: "linear-gradient(180deg, #4F7FFF, #7C6BF0)", borderRadius: "1px", flexShrink: 0 }} />
          <div>
            <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "0.4vh", letterSpacing: "0.05em", textTransform: "uppercase" }}>Praktijkvoorbeeld</div>
            <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>COVID veroorzaakte enorme vraag naar printers en thuiswerkproducten. Geen enkel AI-model had dat vooraf exact kunnen voorspellen. <span style={{ color: "#F0F4FF", fontWeight: 500 }}>AI blijft daarom een adviesinstrument &#8212; menselijke besluitvorming blijft noodzakelijk.</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Slide09Forecasting() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>
      <div className="absolute inset-0" style={{ backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)", backgroundSize: "6vw 6vw" }} />
      <div className="absolute" style={{ width: "40vw", height: "40vw", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.1) 0%, transparent 70%)", bottom: "-12vw", left: "-5vw" }} />

      <div className="absolute" style={{ top: "3.5vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>08 — Forecasting &amp; Procurement</div>
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      <div className="absolute inset-0 flex" style={{ padding: "9vh 5vw 7vh 5vw", gap: "4vw" }}>

        {/* Left */}
        <div style={{ flex: "0 0 44vw", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <h2 style={{ fontSize: "3.8vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "3vh", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
            AI geeft vroege signalen voor inkoop en voorraad
          </h2>
          <p style={{ fontSize: "1.05vw", color: "#8892B0", lineHeight: 1.7, marginBottom: "3.5vh" }}>
            Door externe factoren te monitoren &#8212; grondstoffen, transport, leveranciers, inflatie &#8212; geeft AI tijdig signalen zodat inkoop en logistiek proactief kunnen handelen.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "1.3vh" }}>
            <div style={{ fontSize: "0.9vw", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: "0.3vh" }}>AI ondersteunt beslissingen over</div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
              <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Inkoopvolumes en -timing per categorie</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#7C6BF0", flexShrink: 0 }} />
              <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Voorraadbeslissingen op basis van vraagprognose</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.8vw", padding: "1.2vh 1.4vw", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.6vw" }}>
              <div style={{ width: "0.5vw", height: "0.5vw", borderRadius: "50%", background: "#4F7FFF", flexShrink: 0 }} />
              <span style={{ fontSize: "0.95vw", color: "#8892B0" }}>Kostenontwikkelingen en leveranciersrisico signaleren</span>
            </div>
          </div>
        </div>

        {/* Right: factoren + principe */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: "1.8vh" }}>
          <div style={{ fontSize: "1vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "0.3vh" }}>Gemonitorde externe factoren</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1vw" }}>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", padding: "1.4vh 1.3vw", textAlign: "center" }}>
              <div style={{ fontSize: "0.95vw", fontWeight: 600, color: "#F0F4FF" }}>Grondstoffen</div>
              <div style={{ fontSize: "0.82vw", color: "#8892B0", marginTop: "0.3vh" }}>Papier, inkt, toner</div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.7vw", padding: "1.4vh 1.3vw", textAlign: "center" }}>
              <div style={{ fontSize: "0.95vw", fontWeight: 600, color: "#F0F4FF" }}>Transport</div>
              <div style={{ fontSize: "0.82vw", color: "#8892B0", marginTop: "0.3vh" }}>Kosten, beschikbaarheid</div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.18)", borderRadius: "0.7vw", padding: "1.4vh 1.3vw", textAlign: "center" }}>
              <div style={{ fontSize: "0.95vw", fontWeight: 600, color: "#F0F4FF" }}>Leveranciers</div>
              <div style={{ fontSize: "0.82vw", color: "#8892B0", marginTop: "0.3vh" }}>Levertijden, risico's</div>
            </div>
            <div style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(124,107,240,0.18)", borderRadius: "0.7vw", padding: "1.4vh 1.3vw", textAlign: "center" }}>
              <div style={{ fontSize: "0.95vw", fontWeight: 600, color: "#F0F4FF" }}>Inflatie</div>
              <div style={{ fontSize: "0.82vw", color: "#8892B0", marginTop: "0.3vh" }}>Kostprijsontwikkeling</div>
            </div>
          </div>

          <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.1), rgba(124,107,240,0.1))", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "0.8vw", padding: "2vh 1.8vw", marginTop: "0.5vh" }}>
            <div style={{ fontSize: "0.85vw", color: "#4F7FFF", fontWeight: 700, marginBottom: "0.6vh" }}>Kernprincipe</div>
            <div style={{ fontSize: "0.95vw", color: "#8892B0", lineHeight: 1.55 }}>AI geeft signalen &#8212; de mens bepaalt de uiteindelijke actie.</div>
          </div>
        </div>
      </div>
    </div>
  );
}

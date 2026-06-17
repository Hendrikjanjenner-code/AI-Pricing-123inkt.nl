export default function Slide2Probleem() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Grid texture */}
      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.05) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      {/* Glow */}
      <div className="absolute" style={{
        width: "40vw", height: "40vw", borderRadius: "50%",
        background: "radial-gradient(circle, rgba(124,107,240,0.12) 0%, transparent 70%)",
        bottom: "-10vw", right: "-5vw"
      }} />

      {/* Slide number */}
      <div className="absolute" style={{ top: "4vh", left: "5vw", color: "#4F7FFF", fontSize: "0.9vw", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase" }}>01 — Het Probleem</div>

      {/* Bottom line */}
      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.3vh", background: "linear-gradient(90deg, transparent, #4F7FFF, #7C6BF0, transparent)" }} />

      {/* Content */}
      <div className="absolute inset-0 flex flex-col justify-center" style={{ padding: "10vh 5vw 8vh 5vw" }}>

        <h2 style={{ fontSize: "4vw", fontWeight: 800, color: "#F0F4FF", marginBottom: "5vh", letterSpacing: "-0.02em", textWrap: "balance", lineHeight: 1.1 }}>
          Handmatig prijsbeheer schaalt niet
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "2.5vw" }}>

          {/* Card 1 */}
          <div style={{
            background: "rgba(20,24,40,0.8)",
            border: "1px solid rgba(79,127,255,0.18)",
            borderRadius: "1vw",
            padding: "3.5vh 2.2vw"
          }}>
            <div style={{
              width: "3.2vw", height: "3.2vw", borderRadius: "0.6vw",
              background: "rgba(79,127,255,0.15)",
              border: "1px solid rgba(79,127,255,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: "2.5vh"
            }}>
              <svg width="45%" height="45%" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="#4F7FFF" strokeWidth="2"/>
                <path d="M12 7v5l3 3" stroke="#4F7FFF" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
            <div style={{ fontSize: "1.3vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh", lineHeight: 1.2 }}>Tijdsintensief</div>
            <div style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.6 }}>
              Prijsanalisten besteden dagelijks uren aan handmatige checks op duizenden SKU's — structureel onhoudbaar bij groei.
            </div>
          </div>

          {/* Card 2 */}
          <div style={{
            background: "rgba(20,24,40,0.8)",
            border: "1px solid rgba(124,107,240,0.18)",
            borderRadius: "1vw",
            padding: "3.5vh 2.2vw"
          }}>
            <div style={{
              width: "3.2vw", height: "3.2vw", borderRadius: "0.6vw",
              background: "rgba(124,107,240,0.15)",
              border: "1px solid rgba(124,107,240,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: "2.5vh"
            }}>
              <svg width="45%" height="45%" viewBox="0 0 24 24" fill="none">
                <path d="M3 3h18v4H3V3zm0 7h12v4H3v-4zm0 7h8v4H3v-4z" stroke="#7C6BF0" strokeWidth="2" strokeLinejoin="round"/>
              </svg>
            </div>
            <div style={{ fontSize: "1.3vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh", lineHeight: 1.2 }}>Inconsistente strategie</div>
            <div style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.6 }}>
              Zonder gestructureerde regels leidt elk categorieteam zijn eigen aanpak — margedoelen en concurrentiepositie botsen.
            </div>
          </div>

          {/* Card 3 */}
          <div style={{
            background: "rgba(20,24,40,0.8)",
            border: "1px solid rgba(79,127,255,0.18)",
            borderRadius: "1vw",
            padding: "3.5vh 2.2vw"
          }}>
            <div style={{
              width: "3.2vw", height: "3.2vw", borderRadius: "0.6vw",
              background: "rgba(79,127,255,0.15)",
              border: "1px solid rgba(79,127,255,0.25)",
              display: "flex", alignItems: "center", justifyContent: "center",
              marginBottom: "2.5vh"
            }}>
              <svg width="45%" height="45%" viewBox="0 0 24 24" fill="none">
                <path d="M2 20l5-10 4 6 3-4 6 8H2z" stroke="#4F7FFF" strokeWidth="2" strokeLinejoin="round"/>
              </svg>
            </div>
            <div style={{ fontSize: "1.3vw", fontWeight: 700, color: "#F0F4FF", marginBottom: "1.5vh", lineHeight: 1.2 }}>Gemiste kansen</div>
            <div style={{ fontSize: "1vw", color: "#8892B0", lineHeight: 1.6 }}>
              Concurrenten reageren in uren; ons team reageert in dagen. Elke dag vertraging kost marge en marktaandeel.
            </div>
          </div>
        </div>

        {/* Bottom stat bar */}
        <div style={{
          marginTop: "4vh",
          padding: "2vh 2.5vw",
          background: "rgba(79,127,255,0.08)",
          border: "1px solid rgba(79,127,255,0.15)",
          borderRadius: "0.8vw",
          display: "flex",
          alignItems: "center",
          gap: "1vw"
        }}>
          <div style={{ width: "0.3vw", height: "3.5vh", background: "#4F7FFF", borderRadius: "1px", flexShrink: 0 }} />
          <p style={{ fontSize: "1.1vw", color: "#8892B0", margin: 0, lineHeight: 1.5 }}>
            <span style={{ color: "#F0F4FF", fontWeight: 600 }}>26.000+ actieve SKU's</span> over 9 categorieen — elk met eigen margedoelen, concurrentiepositie en vraagprofiel. Handmatig beheer is structureel onhoudbaar.
          </p>
        </div>
      </div>
    </div>
  );
}

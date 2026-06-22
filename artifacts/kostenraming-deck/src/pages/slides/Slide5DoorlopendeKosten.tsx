export default function Slide5DoorlopendeKosten() {
  return (
    <div className="relative w-screen h-screen overflow-hidden" style={{ background: "#0C0F1A", fontFamily: "Inter, system-ui, sans-serif" }}>

      <div className="absolute inset-0" style={{
        backgroundImage: "linear-gradient(rgba(79,127,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.04) 1px, transparent 1px)",
        backgroundSize: "6vw 6vw"
      }} />

      <div className="absolute top-0 left-0 right-0 flex items-center justify-between" style={{ padding: "3vh 6vw" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.7vw" }}>
          <div style={{ width: "1.6vw", height: "1.6vw", borderRadius: "0.3vw", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)" }} />
          <span style={{ color: "#8892B0", fontSize: "1vw", fontWeight: 400 }}>123inkt</span>
        </div>
        <span style={{ color: "#8892B0", fontSize: "0.95vw" }}>Vertrouwelijk — Directie</span>
      </div>

      <div className="absolute" style={{ top: "12vh", left: "6vw", right: "6vw" }}>
        <div style={{ width: "3.5vw", height: "0.35vh", background: "#4F7FFF", marginBottom: "1.8vh" }} />
        <h2 style={{ fontSize: "3.2vw", fontWeight: 700, color: "#F0F4FF", lineHeight: 1.2, textWrap: "balance", maxWidth: "78vw" }}>
          Doorlopende kosten van €6.200/maand zijn stabiel na pilotafronding
        </h2>
      </div>

      {/* Two-column layout */}
      <div className="absolute" style={{ top: "31vh", left: "6vw", right: "6vw", display: "flex", gap: "4vw" }}>

        {/* Table */}
        <div style={{ flex: "0 0 58vw" }}>
          {/* Header */}
          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.2vh 2vw", background: "#141828", borderRadius: "0.4vw 0.4vw 0 0", borderBottom: "1px solid rgba(79,127,255,0.3)" }}>
            <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Post</span>
            <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Omschrijving</span>
            <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase", textAlign: "right" }}>Per maand</span>
            <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase", textAlign: "right" }}>Jaarlijks</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>PriceShape licentie</span>
            <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>SaaS-abonnement tot 1.000 SKU's</span>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€2.000</span>
            <span style={{ fontSize: "1.7vw", color: "#8892B0", textAlign: "right" }}>€24.000</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.5vh 2vw", background: "#0C0F1A", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Cloud infra (AWS)</span>
            <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>ECS compute, RDS, S3 opslag</span>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€1.800</span>
            <span style={{ fontSize: "1.7vw", color: "#8892B0", textAlign: "right" }}>€21.600</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.1)" }}>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Beheer & onderhoud</span>
            <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>0,5 FTE data engineering</span>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€2.000</span>
            <span style={{ fontSize: "1.7vw", color: "#8892B0", textAlign: "right" }}>€24.000</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.5vh 2vw", background: "#0C0F1A", borderBottom: "1px solid rgba(79,127,255,0.3)" }}>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF" }}>Monitoring & support</span>
            <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>Alerting, incident response SLA</span>
            <span style={{ fontSize: "1.7vw", color: "#F0F4FF", textAlign: "right", fontWeight: 700 }}>€400</span>
            <span style={{ fontSize: "1.7vw", color: "#8892B0", textAlign: "right" }}>€4.800</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "3fr 4fr 1.8fr 1.8fr", padding: "1.8vh 2vw", background: "#141828", borderRadius: "0 0 0.4vw 0.4vw" }}>
            <span style={{ fontSize: "1.9vw", color: "#F0F4FF", fontWeight: 700 }}>Totaal doorlopend</span>
            <span style={{ fontSize: "1.6vw", color: "#8892B0" }}>Na pilotafronding</span>
            <span style={{ fontSize: "2vw", color: "#4F7FFF", textAlign: "right", fontWeight: 700 }}>€6.200</span>
            <span style={{ fontSize: "2vw", color: "#4F7FFF", textAlign: "right", fontWeight: 700 }}>€74.400</span>
          </div>

          <div style={{ fontSize: "1.2vw", color: "#8892B0", marginTop: "1.5vh", opacity: 0.7 }}>
            Bron: AWS prijsmodel juni 2026, PriceShape tariefblad Q2 2026
          </div>
        </div>

        {/* Right: note on scaling */}
        <div style={{ flex: 1 }}>
          <div style={{ background: "#141828", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "0.5vw", padding: "3vh 2vw" }}>
            <div style={{ fontSize: "1vw", fontWeight: 700, color: "#4F7FFF", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "1.5vh" }}>Schaalbaarheid</div>
            <div style={{ fontSize: "1.7vw", color: "#F0F4FF", lineHeight: 1.55, marginBottom: "1.5vh" }}>
              Bij uitrol naar 26.000+ SKU's stijgen de PriceShape-kosten naar het enterprise-tarief (indicatief €8.500/mnd).
            </div>
            <div style={{ fontSize: "1.7vw", color: "#8892B0", lineHeight: 1.55 }}>
              AWS-kosten schalen lineair mee; verwacht circa €6.000/mnd bij volledige uitrol.
            </div>
          </div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>5 / 9</span>
      </div>
    </div>
  );
}

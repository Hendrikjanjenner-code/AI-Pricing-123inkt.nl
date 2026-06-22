export default function Slide7Risicos() {
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
          Drie hoofdrisico's zijn geïdentificeerd; elk heeft een concrete mitigatie
        </h2>
      </div>

      {/* Risk table */}
      <div className="absolute" style={{ top: "31vh", left: "6vw", right: "6vw" }}>

        {/* Header */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 1.2fr 1.2fr 4fr", padding: "1.2vh 2vw", background: "#141828", borderRadius: "0.4vw 0.4vw 0 0", borderBottom: "1px solid rgba(79,127,255,0.3)" }}>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Risico</span>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Kans</span>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Impact</span>
          <span style={{ fontSize: "1.3vw", fontWeight: 700, color: "#8892B0", letterSpacing: "0.05em", textTransform: "uppercase" }}>Mitigatie</span>
        </div>

        {/* Row 1 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 1.2fr 1.2fr 4fr", padding: "2.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.12)", alignItems: "start" }}>
          <div>
            <div style={{ fontSize: "1.8vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.3 }}>Datakwaliteit productie</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", lineHeight: 1.4, marginTop: "0.5vh" }}>Ontbrekende of inconsistente kostenprijs-data vertraagt model-convergentie</div>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.4)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#F59E0B", fontWeight: 700 }}>Middel</span>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#EF4444", fontWeight: 700 }}>Hoog</span>
          </div>
          <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.5 }}>
            Data-kwaliteitscheck ingebouwd in fase 1; pilot start pas bij &gt;90% dekking kostprijs op pilotSKU's.
          </div>
        </div>

        {/* Row 2 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 1.2fr 1.2fr 4fr", padding: "2.5vh 2vw", background: "#0C0F1A", borderBottom: "1px solid rgba(79,127,255,0.12)", alignItems: "start" }}>
          <div>
            <div style={{ fontSize: "1.8vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.3 }}>PriceShape API-wijzigingen</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", lineHeight: 1.4, marginTop: "0.5vh" }}>Breaking changes in externe API onderbreken de export-feed</div>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(34,197,94,0.12)", border: "1px solid rgba(34,197,94,0.35)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#22C55E", fontWeight: 700 }}>Laag</span>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.4)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#F59E0B", fontWeight: 700 }}>Middel</span>
          </div>
          <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.5 }}>
            Contract bevat 30-dagen-notificatie SLA bij API-wijzigingen; integratie via versioneerde webhook.
          </div>
        </div>

        {/* Row 3 */}
        <div style={{ display: "grid", gridTemplateColumns: "3fr 1.2fr 1.2fr 4fr", padding: "2.5vh 2vw", background: "#0F1422", borderBottom: "1px solid rgba(79,127,255,0.2)", alignItems: "start" }}>
          <div>
            <div style={{ fontSize: "1.8vw", color: "#F0F4FF", fontWeight: 700, lineHeight: 1.3 }}>Marge-uplift valt lager uit</div>
            <div style={{ fontSize: "1.5vw", color: "#8892B0", lineHeight: 1.4, marginTop: "0.5vh" }}>Model behaalt &lt;2% uplift op pilotSKU's — ROI-drempel niet gehaald</div>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(245,158,11,0.15)", border: "1px solid rgba(245,158,11,0.4)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#F59E0B", fontWeight: 700 }}>Middel</span>
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            <span style={{ display: "inline-block", background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.35)", borderRadius: "0.3vw", padding: "0.4vh 0.8vw", fontSize: "1.5vw", color: "#EF4444", fontWeight: 700 }}>Hoog</span>
          </div>
          <div style={{ fontSize: "1.6vw", color: "#8892B0", lineHeight: 1.5 }}>
            Go/no-go na fase 2 (week 8) op basis van tussentijdse KPI's; budget fase 3 alleen bij positieve tussenstand.
          </div>
        </div>

        <div style={{ fontSize: "1.2vw", color: "#8892B0", marginTop: "1.5vh", opacity: 0.7 }}>
          Risicobeoordeling: intern Pricing & Technology team — juni 2026
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0" style={{ height: "0.15vh", background: "rgba(79,127,255,0.2)" }} />
      <div className="absolute bottom-0 left-0 right-0 flex items-end justify-between" style={{ padding: "0 6vw 2.5vh" }}>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>Vertrouwelijk — 123inkt</span>
        <span style={{ color: "#8892B0", fontSize: "1vw", opacity: 0.6 }}>7 / 9</span>
      </div>
    </div>
  );
}

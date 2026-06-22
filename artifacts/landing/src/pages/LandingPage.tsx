export default function LandingPage() {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");

  return (
    <div style={{ background: "#0C0F1A", color: "#F0F4FF", fontFamily: "Inter, system-ui, sans-serif", minHeight: "100vh", overflowX: "hidden" }}>

      {/* ── NAVIGATION ── */}
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 50,
        background: "rgba(12,15,26,0.85)",
        backdropFilter: "blur(20px)",
        borderBottom: "1px solid rgba(79,127,255,0.12)",
        padding: "0 max(5vw, 24px)"
      }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", height: "64px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{
              width: "34px", height: "34px", borderRadius: "8px",
              background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
              display: "flex", alignItems: "center", justifyContent: "center"
            }}>
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
                <path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.95"/>
              </svg>
            </div>
            <span style={{ fontWeight: 700, fontSize: "1.05rem", color: "#F0F4FF" }}>AI Pricing Engine</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "32px" }}>
            <a href="#modules" style={{ color: "#8892B0", fontSize: "0.9rem", textDecoration: "none", fontWeight: 500 }}>Modules</a>
            <a href="#resultaten" style={{ color: "#8892B0", fontSize: "0.9rem", textDecoration: "none", fontWeight: 500 }}>Resultaten</a>
            <a href="#strategie" style={{ color: "#8892B0", fontSize: "0.9rem", textDecoration: "none", fontWeight: 500 }}>Strategie</a>
            <a
              href={`${base}/`}
              style={{
                background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
                color: "white", fontSize: "0.9rem", fontWeight: 600,
                padding: "8px 20px", borderRadius: "8px", textDecoration: "none"
              }}
            >
              Open platform
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section style={{ position: "relative", minHeight: "100vh", display: "flex", alignItems: "center", paddingTop: "64px", overflow: "hidden" }}>

        {/* Background grid */}
        <div style={{
          position: "absolute", inset: 0,
          backgroundImage: "linear-gradient(rgba(79,127,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(79,127,255,0.06) 1px, transparent 1px)",
          backgroundSize: "60px 60px"
        }} />

        {/* Glow orbs */}
        <div style={{ position: "absolute", width: "700px", height: "700px", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.15) 0%, transparent 70%)", top: "-200px", right: "-150px" }} />
        <div style={{ position: "absolute", width: "500px", height: "500px", borderRadius: "50%", background: "radial-gradient(circle, rgba(124,107,240,0.12) 0%, transparent 70%)", bottom: "-150px", left: "-100px" }} />

        <div style={{ position: "relative", maxWidth: "1280px", margin: "0 auto", padding: "0 max(5vw, 24px)", width: "100%" }}>
          <div style={{ maxWidth: "760px" }}>
            <div style={{
              display: "inline-flex", alignItems: "center", gap: "8px",
              background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.25)",
              borderRadius: "999px", padding: "6px 16px", marginBottom: "32px"
            }}>
              <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#4F7FFF" }} />
              <span style={{ color: "#4F7FFF", fontSize: "0.85rem", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Production-ready platform</span>
            </div>

            <h1 style={{
              fontSize: "clamp(2.8rem, 6vw, 5.5rem)", fontWeight: 900,
              lineHeight: 1.05, letterSpacing: "-0.03em",
              color: "#F0F4FF", marginBottom: "24px", textWrap: "balance"
            }}>
              Slimmer prijzen.<br />
              <span style={{ background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                Meer marge.
              </span>
            </h1>

            <p style={{ fontSize: "clamp(1rem, 1.8vw, 1.25rem)", color: "#8892B0", lineHeight: 1.7, marginBottom: "48px", maxWidth: "580px" }}>
              Het AI Pricing Decision Engine genereert dagelijks prijsaanbevelingen voor elk SKU — op basis van concurrentie, marge, voorraad en strategie. Analisten keuren goed in minuten, niet uren.
            </p>

            <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
              <a
                href={`${base}/`}
                style={{
                  background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
                  color: "white", fontWeight: 700, fontSize: "1rem",
                  padding: "14px 32px", borderRadius: "10px", textDecoration: "none",
                  boxShadow: "0 0 30px rgba(79,127,255,0.3)"
                }}
              >
                Open het platform
              </a>
              <a
                href="#modules"
                style={{
                  background: "rgba(79,127,255,0.1)", border: "1px solid rgba(79,127,255,0.25)",
                  color: "#F0F4FF", fontWeight: 600, fontSize: "1rem",
                  padding: "14px 32px", borderRadius: "10px", textDecoration: "none"
                }}
              >
                Meer weten
              </a>
            </div>
          </div>

          {/* Hero stats */}
          <div style={{ display: "flex", gap: "40px", marginTop: "80px", flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: "2.8rem", fontWeight: 900, color: "#4F7FFF", lineHeight: 1 }}>+4,2%</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "6px", fontWeight: 500 }}>Brutomarge uplift</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)" }} />
            <div>
              <div style={{ fontSize: "2.8rem", fontWeight: 900, color: "#7C6BF0", lineHeight: 1 }}>−70%</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "6px", fontWeight: 500 }}>Minder handmatig werk</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)" }} />
            <div>
              <div style={{ fontSize: "2.8rem", fontWeight: 900, color: "#4F7FFF", lineHeight: 1 }}>8</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "6px", fontWeight: 500 }}>AI-prijsstrategieën</div>
            </div>
            <div style={{ width: "1px", background: "rgba(79,127,255,0.2)" }} />
            <div>
              <div style={{ fontSize: "2.8rem", fontWeight: 900, color: "#7C6BF0", lineHeight: 1 }}>26K+</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "6px", fontWeight: 500 }}>SKU's ondersteund</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section style={{ padding: "100px max(5vw, 24px)", background: "rgba(20,24,40,0.5)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "64px" }}>
            <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "16px" }}>Werkwijze</div>
            <h2 style={{ fontSize: "clamp(2rem, 3.5vw, 2.8rem)", fontWeight: 800, color: "#F0F4FF", margin: 0, letterSpacing: "-0.02em" }}>Van data tot live prijs in vier stappen</h2>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "24px" }}>
            {[
              { num: "01", title: "Data-ingest", desc: "Verkoop, voorraad, concurrentprijzen en historische data worden dagelijks geladen via CSV-upload of directe koppeling.", color: "#4F7FFF" },
              { num: "02", title: "AI-prijsmotor", desc: "8 geoptimaliseerde strategieën berekenen de ideale prijs per SKU, met veiligheidsregels en een confidence score.", color: "#7C6BF0" },
              { num: "03", title: "Analist-review", desc: "Pricing analisten zien alle aanbevelingen in één cockpit — inclusief uitleg, factoren en audittrail — en keuren goed of verwerpen.", color: "#4F7FFF" },
              { num: "04", title: "Publicatie", desc: "Goedgekeurde prijzen worden rechtstreeks gepubliceerd via de interne prijsmodule en zijn binnen minuten live in de webshop.", color: "#7C6BF0" },
            ].map((step) => (
              <div key={step.num} style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "16px", padding: "32px 28px" }}>
                <div style={{ fontSize: "2.5rem", fontWeight: 900, color: step.color, opacity: 0.4, lineHeight: 1, marginBottom: "16px" }}>{step.num}</div>
                <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#F0F4FF", marginBottom: "12px" }}>{step.title}</div>
                <div style={{ fontSize: "0.9rem", color: "#8892B0", lineHeight: 1.7 }}>{step.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── MODULES ── */}
      <section id="modules" style={{ padding: "100px max(5vw, 24px)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "64px" }}>
            <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "16px" }}>Platform</div>
            <h2 style={{ fontSize: "clamp(2rem, 3.5vw, 2.8rem)", fontWeight: 800, color: "#F0F4FF", margin: 0, letterSpacing: "-0.02em" }}>Tien geïntegreerde modules</h2>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "20px" }}>
            {[
              { icon: "📊", title: "Dashboard", desc: "KPI-overzicht, margegrafieken, real-time aanbevelingsstatus" },
              { icon: "✓", title: "Aanbevelingen", desc: "Filteren, bulk-goedkeuren, detail-view per SKU" },
              { icon: "□", title: "SKU-beheer", desc: "Productcatalogus, prijshistorie en deep-dive analyse" },
              { icon: "◈", title: "Categoriestrategie", desc: "8 strategieën configureerbaar per categorie" },
              { icon: "↑", title: "Data-upload", desc: "8 CSV-types met validatie en importhistorie" },
              { icon: "!", title: "Datakwaliteit", desc: "Kwaliteitsscore, issues-overzicht en automatische alerts" },
              { icon: "◎", title: "Concurrentie", desc: "PCIS-scores, prijsindex en concurrentanalyse per SKU" },
              { icon: "≡", title: "A/B-testen", desc: "AI vs. controlgroep met statistische significantie" },
              { icon: "⊡", title: "Modelgezondheid", desc: "Laatste run bekijken en nieuwe run handmatig triggeren" },
              { icon: "★", title: "Explainability", desc: "Uitleg per aanbeveling, factoren en volledige audittrail" },
            ].map((mod, i) => (
              <div key={i} style={{
                background: "rgba(20,24,40,0.8)",
                border: i === 9 ? "1px solid rgba(79,127,255,0.4)" : "1px solid rgba(79,127,255,0.12)",
                borderRadius: "14px", padding: "28px 24px",
                background: i === 9 ? "rgba(79,127,255,0.08)" : "rgba(20,24,40,0.8)"
              }}>
                <div style={{ fontSize: "1.4rem", marginBottom: "12px", opacity: 0.8 }}>{mod.icon}</div>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: i === 9 ? "#4F7FFF" : "#F0F4FF", marginBottom: "8px" }}>{mod.title}</div>
                <div style={{ fontSize: "0.85rem", color: "#8892B0", lineHeight: 1.6 }}>{mod.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── STRATEGIES ── */}
      <section id="strategie" style={{ padding: "100px max(5vw, 24px)", background: "rgba(20,24,40,0.5)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "80px", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "16px" }}>Strategieën</div>
              <h2 style={{ fontSize: "clamp(2rem, 3.5vw, 2.8rem)", fontWeight: 800, color: "#F0F4FF", marginBottom: "24px", letterSpacing: "-0.02em", textWrap: "balance" }}>
                Acht strategieën voor elke SKU-situatie
              </h2>
              <p style={{ fontSize: "1rem", color: "#8892B0", lineHeight: 1.8, marginBottom: "32px" }}>
                Elke categorie krijgt de strategie die past bij haar concurrentiepositie en margedoelstelling. Van A-merk/private-label optimalisatie tot clearance-pricing — het systeem past zich automatisch aan.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {[
                  "Veiligheidsregels gebakken in elke strategie",
                  "Configureerbaar per categorie via het dashboard",
                  "Confidence score waarschuwt bij lage zekerheid",
                  "Volledige uitlegbaarheid per aanbeveling",
                ].map((item, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <div style={{ width: "20px", height: "20px", borderRadius: "50%", background: "rgba(79,127,255,0.15)", border: "1px solid #4F7FFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M2 6l3 3 5-5" stroke="#4F7FFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </div>
                    <span style={{ fontSize: "0.9rem", color: "#8892B0" }}>{item}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {[
                { name: "Substitution Portfolio", desc: "A-merk / private-label prijskloof optimaliseren" },
                { name: "Competitor Index", desc: "Concurrentiegemiddelde volgen en indexdoel handhaven" },
                { name: "Margin Optimization", desc: "Grid-search voor winstmaximaliserende prijs" },
                { name: "Stock Clearance", desc: "Stapsgewijze korting voor overtollige voorraad" },
                { name: "Basket Builder", desc: "Competitief op basket-driver SKU's blijven" },
                { name: "Volume Discount", desc: "Lagere prijs voor hoge-elasticiteit volume-SKU's" },
                { name: "Repeat Purchase", desc: "Prijsstabiliteit voor terugkerende klanten" },
                { name: "Low Velocity", desc: "Marge beschermen op langzaam-draaiende items" },
              ].map((s, i) => (
                <div key={i} style={{
                  background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.12)",
                  borderRadius: "10px", padding: "16px 20px",
                  display: "flex", alignItems: "center", gap: "16px"
                }}>
                  <div style={{ width: "6px", height: "6px", borderRadius: "50%", background: i % 2 === 0 ? "#4F7FFF" : "#7C6BF0", flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "#F0F4FF" }}>{s.name}</div>
                    <div style={{ fontSize: "0.8rem", color: "#8892B0", marginTop: "3px" }}>{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── RESULTS ── */}
      <section id="resultaten" style={{ padding: "100px max(5vw, 24px)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ textAlign: "center", marginBottom: "64px" }}>
            <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "16px" }}>Bewezen impact</div>
            <h2 style={{ fontSize: "clamp(2rem, 3.5vw, 2.8rem)", fontWeight: 800, color: "#F0F4FF", margin: 0, letterSpacing: "-0.02em" }}>Gemeten op pilotresultaten</h2>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "24px" }}>
            <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.12), rgba(124,107,240,0.08))", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "16px", padding: "40px 32px", textAlign: "center" }}>
              <div style={{ fontSize: "4rem", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>+4,2%</div>
              <div style={{ fontSize: "1.05rem", fontWeight: 600, color: "#F0F4FF", marginTop: "16px" }}>Brutomarge uplift</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "8px" }}>AI-aanbevelingen vs. handmatig beheer</div>
            </div>
            <div style={{ background: "linear-gradient(135deg, rgba(124,107,240,0.12), rgba(79,127,255,0.08))", border: "1px solid rgba(124,107,240,0.25)", borderRadius: "16px", padding: "40px 32px", textAlign: "center" }}>
              <div style={{ fontSize: "4rem", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #7C6BF0, #4F7FFF)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>87%</div>
              <div style={{ fontSize: "1.05rem", fontWeight: 600, color: "#F0F4FF", marginTop: "16px" }}>Goedkeuringspercentage</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "8px" }}>Analisten vertrouwen op het AI-advies</div>
            </div>
            <div style={{ background: "linear-gradient(135deg, rgba(79,127,255,0.12), rgba(124,107,240,0.08))", border: "1px solid rgba(79,127,255,0.25)", borderRadius: "16px", padding: "40px 32px", textAlign: "center" }}>
              <div style={{ fontSize: "4rem", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>&lt;1u</div>
              <div style={{ fontSize: "1.05rem", fontWeight: 600, color: "#F0F4FF", marginTop: "16px" }}>Time-to-market</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0", marginTop: "8px" }}>Van beslissing tot live prijs in de winkel</div>
            </div>
          </div>

          {/* A/B test detail */}
          <div style={{ marginTop: "40px", background: "rgba(20,24,40,0.8)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "16px", padding: "40px 40px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "40px", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "12px" }}>A/B-test resultaten</div>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#F0F4FF", marginBottom: "8px" }}>AI vs. Controle</div>
                <div style={{ fontSize: "0.9rem", color: "#8892B0", lineHeight: 1.7 }}>13 AI-SKU's versus 13 controle-SKU's over 8 weken. Statistische zekerheid: 94%.</div>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "0.85rem", color: "#8892B0" }}>Marge-uplift</span>
                    <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#4F7FFF" }}>+3,8%</span>
                  </div>
                  <div style={{ height: "6px", background: "rgba(79,127,255,0.15)", borderRadius: "3px" }}>
                    <div style={{ width: "76%", height: "100%", background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", borderRadius: "3px" }} />
                  </div>
                </div>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "0.85rem", color: "#8892B0" }}>Conversie-uplift</span>
                    <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#7C6BF0" }}>+1,2%</span>
                  </div>
                  <div style={{ height: "6px", background: "rgba(124,107,240,0.15)", borderRadius: "3px" }}>
                    <div style={{ width: "42%", height: "100%", background: "linear-gradient(90deg, #7C6BF0, #4F7FFF)", borderRadius: "3px" }} />
                  </div>
                </div>
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "0.85rem", color: "#8892B0" }}>Statistische zekerheid</span>
                    <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "#4F7FFF" }}>94%</span>
                  </div>
                  <div style={{ height: "6px", background: "rgba(79,127,255,0.15)", borderRadius: "3px" }}>
                    <div style={{ width: "94%", height: "100%", background: "linear-gradient(90deg, #4F7FFF, #7C6BF0)", borderRadius: "3px" }} />
                  </div>
                </div>
              </div>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "5rem", fontWeight: 900, lineHeight: 1, background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>94%</div>
                <div style={{ fontSize: "0.9rem", color: "#8892B0", marginTop: "8px" }}>Statistisch zeker</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SAFETY ── */}
      <section style={{ padding: "80px max(5vw, 24px)", background: "rgba(20,24,40,0.5)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "80px", alignItems: "center" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
              {[
                { title: "Prijsvloer", desc: "Koopprijs × 1,01 — altijd gewaarborgd, nooit verliesgevend" },
                { title: "Max. dagverandering", desc: "±5% limiet per dag, geen prijsschokken voor klanten" },
                { title: "Out-of-stock block", desc: "Geen aanbeveling bij nulvoorraad (uitzondering: clearance)" },
                { title: "Confidence waarschuwing", desc: "Lage zekerheid (&lt;40%) wordt automatisch gemarkeerd" },
              ].map((item, i) => (
                <div key={i} style={{ background: "rgba(20,24,40,0.9)", border: "1px solid rgba(79,127,255,0.15)", borderRadius: "12px", padding: "24px 20px" }}>
                  <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: i % 2 === 0 ? "#4F7FFF" : "#7C6BF0", marginBottom: "14px" }} />
                  <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "#F0F4FF", marginBottom: "8px" }}>{item.title}</div>
                  <div style={{ fontSize: "0.82rem", color: "#8892B0", lineHeight: 1.6 }}>{item.desc}</div>
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "16px" }}>Veiligheid</div>
              <h2 style={{ fontSize: "clamp(2rem, 3vw, 2.4rem)", fontWeight: 800, color: "#F0F4FF", marginBottom: "20px", letterSpacing: "-0.02em", textWrap: "balance" }}>
                Gebakken veiligheidsregels. Nul fouten.
              </h2>
              <p style={{ fontSize: "1rem", color: "#8892B0", lineHeight: 1.8, marginBottom: "24px" }}>
                Elke aanbeveling passeert meerdere veiligheidscontroles voordat die zichtbaar is voor een analist. Het systeem blokkeert automatisch wat niet door de beugel kan.
              </p>
              <p style={{ fontSize: "1rem", color: "#8892B0", lineHeight: 1.8 }}>
                Bovendien is alles herleidbaar: wie heeft wat goedgekeurd, wanneer, en met welke argumenten. De audittrail is altijd volledig.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={{ padding: "120px max(5vw, 24px)", textAlign: "center", position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", width: "600px", height: "600px", borderRadius: "50%", background: "radial-gradient(circle, rgba(79,127,255,0.15) 0%, transparent 70%)", top: "50%", left: "50%", transform: "translate(-50%, -50%)" }} />
        <div style={{ position: "relative", maxWidth: "700px", margin: "0 auto" }}>
          <h2 style={{ fontSize: "clamp(2.2rem, 4vw, 3.5rem)", fontWeight: 900, color: "#F0F4FF", marginBottom: "24px", letterSpacing: "-0.03em", textWrap: "balance" }}>
            Klaar om te zien hoe het werkt?
          </h2>
          <p style={{ fontSize: "1.1rem", color: "#8892B0", lineHeight: 1.7, marginBottom: "48px" }}>
            Het platform is volledig operationeel. Log in met een demogebruiker en verken alle modules.
          </p>
          <div style={{ display: "flex", gap: "16px", justifyContent: "center", flexWrap: "wrap" }}>
            <a
              href={`${base}/`}
              style={{
                background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)",
                color: "white", fontWeight: 700, fontSize: "1.05rem",
                padding: "16px 40px", borderRadius: "12px", textDecoration: "none",
                boxShadow: "0 0 40px rgba(79,127,255,0.35)"
              }}
            >
              Open het platform
            </a>
          </div>
          <div style={{ marginTop: "40px", display: "flex", gap: "40px", justifyContent: "center", flexWrap: "wrap" }}>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 600, marginBottom: "4px" }}>Admin</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0" }}>admin / admin123</div>
            </div>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: "0.8rem", color: "#7C6BF0", fontWeight: 600, marginBottom: "4px" }}>Pricing Manager</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0" }}>pricing_manager / manager123</div>
            </div>
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: "0.8rem", color: "#4F7FFF", fontWeight: 600, marginBottom: "4px" }}>Analist</div>
              <div style={{ fontSize: "0.85rem", color: "#8892B0" }}>analyst / analyst123</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer style={{ borderTop: "1px solid rgba(79,127,255,0.12)", padding: "40px max(5vw, 24px)" }}>
        <div style={{ maxWidth: "1280px", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "28px", height: "28px", borderRadius: "6px", background: "linear-gradient(135deg, #4F7FFF, #7C6BF0)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2L14 12H2L8 2Z" fill="white" opacity="0.9"/>
              </svg>
            </div>
            <span style={{ fontWeight: 600, fontSize: "0.95rem", color: "#8892B0" }}>AI Pricing Engine — 123inkt Pricing Team</span>
          </div>
          <div style={{ fontSize: "0.8rem", color: "#8892B0", opacity: 0.6 }}>Vertrouwelijk — Intern gebruik</div>
        </div>
      </footer>
    </div>
  );
}

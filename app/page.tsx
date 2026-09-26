"use client";

import { FormEvent, useMemo, useState } from "react";

type PresetId = "compact" | "creator" | "executive";
type AccessoryId = "monitorArm" | "cableTray" | "keyboardTray";
type PlanId = "starter" | "team" | "enterprise";

type Toast = {
  tone: "success" | "info" | "warning";
  message: string;
};

const navItems = [
  { label: "Planner", href: "#planner" },
  { label: "Features", href: "#features" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" }
];

const presets: Record<
  PresetId,
  { label: string; width: number; basePrice: number; description: string }
> = {
  compact: {
    label: "Compact focus",
    width: 120,
    basePrice: 589,
    description: "A tidy 120 cm setup for laptops, small rooms, and quick transitions."
  },
  creator: {
    label: "Creator dual-screen",
    width: 160,
    basePrice: 829,
    description: "A balanced 160 cm desk with space for dual monitors and notebooks."
  },
  executive: {
    label: "Executive command",
    width: 180,
    basePrice: 1049,
    description: "A premium 180 cm workstation for multiple devices and deep work."
  }
};

const accessories: Record<AccessoryId, { label: string; price: number; detail: string }> = {
  monitorArm: {
    label: "Monitor arm",
    price: 119,
    detail: "Align screens at eye level and free up desktop space."
  },
  cableTray: {
    label: "Cable tray",
    price: 49,
    detail: "Keep power bricks and cables routed safely under the desk."
  },
  keyboardTray: {
    label: "Keyboard tray",
    price: 89,
    detail: "Fine tune typing height without changing the desk frame."
  }
};

const plans: Record<
  PlanId,
  { label: string; price: string; description: string; features: string[]; badge?: string }
> = {
  starter: {
    label: "Starter",
    price: "$99",
    description: "Self-guided checklist for one room or home office.",
    features: ["Desk fit checklist", "Cable map", "Posture quick-start guide"]
  },
  team: {
    label: "Team",
    price: "$399",
    badge: "Most popular",
    description: "Guided planning session for up to 20 workstations.",
    features: ["Everything in Starter", "60-minute consultation", "Team rollout plan"]
  },
  enterprise: {
    label: "Enterprise",
    price: "Custom",
    description: "Full workspace audit with procurement and rollout support.",
    features: ["Multi-site assessment", "Procurement shortlist", "Dedicated ergonomics lead"]
  }
};

const faqItems = [
  {
    question: "Can SwingDesk work with our existing desks?",
    answer:
      "Yes. The planner can be used for new purchases or retrofits. During an audit, we measure the current layout and recommend only the parts that create a measurable ergonomic improvement."
  },
  {
    question: "How fast can we get a recommendation?",
    answer:
      "The on-page planner creates an instant estimate. If you request a consultation, the form confirms the request immediately and a project brief is ready to hand to your team."
  },
  {
    question: "Are prices final quotes?",
    answer:
      "Planner prices are guide estimates so teams can compare configurations quickly. Final quotes depend on location, volume, finishes, and installation requirements."
  }
];

const checklistText = `SwingDesk workspace checklist

1. Measure available wall and room depth.
2. Confirm preferred desktop width and finish.
3. Check monitor count, laptop docks, and cable paths.
4. Choose accessories: monitor arm, cable tray, keyboard tray.
5. Schedule a posture review after installation.`;

function scrollToSection(sectionId: string) {
  const section = document.getElementById(sectionId);
  if (section) {
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function currency(amount: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(amount);
}

export default function Home() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [auditOpen, setAuditOpen] = useState(false);
  const [preset, setPreset] = useState<PresetId>("creator");
  const [selectedAccessories, setSelectedAccessories] = useState<AccessoryId[]>([
    "monitorArm",
    "cableTray"
  ]);
  const [toast, setToast] = useState<Toast | null>(null);
  const [comparePlans, setComparePlans] = useState(false);
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [form, setForm] = useState({
    name: "",
    email: "",
    company: "",
    plan: "Team",
    message: "I would like help planning ergonomic standing desks for my team."
  });
  const [formStatus, setFormStatus] = useState<"idle" | "sent">("idle");

  const selectedPreset = presets[preset];
  const accessoriesTotal = selectedAccessories.reduce(
    (total, accessoryId) => total + accessories[accessoryId].price,
    0
  );
  const setupTotal = selectedPreset.basePrice + accessoriesTotal;

  const selectedAccessoryLabels = useMemo(
    () => selectedAccessories.map((accessoryId) => accessories[accessoryId].label),
    [selectedAccessories]
  );

  const summary = `${selectedPreset.label} desk, ${selectedPreset.width} cm wide, ${
    selectedAccessoryLabels.length
      ? selectedAccessoryLabels.join(", ")
      : "no add-on accessories"
  }. Estimated package: ${currency(setupTotal)}.`;

  function showToast(message: string, tone: Toast["tone"] = "success") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 3200);
  }

  function handleNavClick(href: string) {
    setMobileMenuOpen(false);
    scrollToSection(href.replace("#", ""));
  }

  function toggleAccessory(accessoryId: AccessoryId) {
    setSelectedAccessories((current) =>
      current.includes(accessoryId)
        ? current.filter((item) => item !== accessoryId)
        : [...current, accessoryId]
    );
  }

  function handleSaveConfiguration() {
    const savedConfig = {
      preset,
      accessories: selectedAccessories,
      total: setupTotal,
      savedAt: new Date().toISOString()
    };
    localStorage.setItem("swingdesk-configuration", JSON.stringify(savedConfig));
    showToast("Configuration saved in this browser.");
  }

  async function handleCopySummary() {
    try {
      await navigator.clipboard.writeText(summary);
      showToast("Desk summary copied to clipboard.");
    } catch {
      showToast("Clipboard access was blocked. Select the summary text manually.", "warning");
    }
  }

  function handleEmailRecommendation() {
    setForm((current) => ({
      ...current,
      plan: "Team",
      message: `Please prepare a recommendation based on this setup: ${summary}`
    }));
    scrollToSection("contact");
    showToast("Recommendation details added to the contact form.", "info");
  }

  function handleSelectPlan(planId: PlanId) {
    const plan = plans[planId];
    setForm((current) => ({
      ...current,
      plan: plan.label,
      message: `I am interested in the ${plan.label} plan. Please contact me with next steps.`
    }));
    scrollToSection("contact");
    showToast(`${plan.label} plan selected. Complete the form to continue.`, "info");
  }

  function handleDownloadChecklist() {
    const blob = new Blob([checklistText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "swingdesk-workspace-checklist.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    showToast("Checklist download started.");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const missingFields = !form.name.trim() || !form.email.trim() || !form.message.trim();
    if (missingFields) {
      showToast("Please add your name, email, and project details.", "warning");
      return;
    }
    setFormStatus("sent");
    showToast("Request submitted. We prepared your handoff summary.");
  }

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" onClick={() => scrollToSection("top")}>
          <span className="brand-mark">SD</span>
          <span>SwingDesk</span>
        </a>

        <nav className="desktop-nav" aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              className="nav-link"
              data-action={`nav-${item.label.toLowerCase()}`}
              key={item.href}
              type="button"
              onClick={() => handleNavClick(item.href)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="header-actions">
          <button
            className="ghost-button"
            data-action="download-checklist"
            type="button"
            onClick={handleDownloadChecklist}
          >
            Download checklist
          </button>
          <button
            className="primary-button"
            data-action="request-consultation"
            type="button"
            onClick={() => scrollToSection("contact")}
          >
            Request consultation
          </button>
          <button
            className="menu-button"
            data-action="toggle-mobile-menu"
            type="button"
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            ☰
          </button>
        </div>
      </header>

      {mobileMenuOpen ? (
        <nav className="mobile-nav" aria-label="Mobile navigation">
          {navItems.map((item) => (
            <button
              className="nav-link"
              data-action={`mobile-nav-${item.label.toLowerCase()}`}
              key={item.href}
              type="button"
              onClick={() => handleNavClick(item.href)}
            >
              {item.label}
            </button>
          ))}
          <button
            className="primary-button"
            data-action="mobile-request-consultation"
            type="button"
            onClick={() => {
              setMobileMenuOpen(false);
              scrollToSection("contact");
            }}
          >
            Request consultation
          </button>
        </nav>
      ) : null}

      <section id="top" className="hero-section section-shell">
        <div className="hero-copy">
          <p className="eyebrow">Workspace planning for flexible teams</p>
          <h1>Build a standing desk setup your team will actually use.</h1>
          <p className="hero-text">
            SwingDesk turns workspace measurements, accessory choices, and budget guardrails into
            a clear procurement handoff. Every button on this handoff is wired to an action you can
            test in the browser.
          </p>
          <div className="button-row">
            <button
              className="primary-button large"
              data-action="hero-open-planner"
              type="button"
              onClick={() => scrollToSection("planner")}
            >
              Plan my desk
            </button>
            <button
              className="secondary-button large"
              data-action="hero-watch-demo"
              type="button"
              onClick={() => setDemoOpen(true)}
            >
              Watch demo
            </button>
          </div>
          <div className="trust-row" aria-label="Key metrics">
            <span>4.9/5 team rating</span>
            <span>24 hour handoff</span>
            <span>ADA-aware planning</span>
          </div>
        </div>
        <div className="hero-card" aria-label="Desk setup preview">
          <div className="desk-preview">
            <div className="monitor monitor-left" />
            <div className="monitor monitor-right" />
            <div className="desk-top" />
            <div className="desk-leg left" />
            <div className="desk-leg right" />
          </div>
          <div className="hero-card-footer">
            <div>
              <span className="muted">Current estimate</span>
              <strong>{currency(setupTotal)}</strong>
            </div>
            <button
              className="mini-button"
              data-action="hero-save-configuration"
              type="button"
              onClick={handleSaveConfiguration}
            >
              Save setup
            </button>
          </div>
        </div>
      </section>

      <section id="planner" className="planner-section section-shell">
        <div className="section-heading">
          <p className="eyebrow">Interactive planner</p>
          <h2>Choose a desk profile, add accessories, and export the recommendation.</h2>
        </div>

        <div className="planner-grid">
          <div className="panel">
            <h3>1. Select a desk profile</h3>
            <div className="option-grid">
              {(Object.keys(presets) as PresetId[]).map((presetId) => {
                const item = presets[presetId];
                const active = preset === presetId;
                return (
                  <button
                    className={`option-card ${active ? "active" : ""}`}
                    data-action={`select-preset-${presetId}`}
                    key={presetId}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setPreset(presetId)}
                  >
                    <span>{item.label}</span>
                    <strong>{item.width} cm</strong>
                    <small>{item.description}</small>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="panel">
            <h3>2. Add ergonomic accessories</h3>
            <div className="accessory-list">
              {(Object.keys(accessories) as AccessoryId[]).map((accessoryId) => {
                const item = accessories[accessoryId];
                const active = selectedAccessories.includes(accessoryId);
                return (
                  <button
                    className={`accessory-row ${active ? "active" : ""}`}
                    data-action={`toggle-accessory-${accessoryId}`}
                    key={accessoryId}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleAccessory(accessoryId)}
                  >
                    <span className="toggle-dot" aria-hidden="true" />
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.detail}</small>
                    </span>
                    <b>+{currency(item.price)}</b>
                  </button>
                );
              })}
            </div>
          </div>

          <aside className="summary-card">
            <p className="eyebrow">Handoff summary</p>
            <h3>{selectedPreset.label}</h3>
            <p>{summary}</p>
            <div className="summary-total">
              <span>Estimated package</span>
              <strong>{currency(setupTotal)}</strong>
            </div>
            <div className="summary-actions">
              <button
                className="primary-button"
                data-action="planner-save-configuration"
                type="button"
                onClick={handleSaveConfiguration}
              >
                Save configuration
              </button>
              <button
                className="secondary-button"
                data-action="planner-copy-summary"
                type="button"
                onClick={handleCopySummary}
              >
                Copy summary
              </button>
              <button
                className="ghost-button"
                data-action="planner-email-recommendation"
                type="button"
                onClick={handleEmailRecommendation}
              >
                Email recommendation
              </button>
            </div>
          </aside>
        </div>
      </section>

      <section id="features" className="features-section section-shell">
        <div className="section-heading split">
          <div>
            <p className="eyebrow">What is included</p>
            <h2>Everything needed to turn desk ideas into a buildable plan.</h2>
          </div>
          <button
            className="secondary-button"
            data-action="features-book-audit"
            type="button"
            onClick={() => setAuditOpen(true)}
          >
            Book workspace audit
          </button>
        </div>

        <div className="feature-grid">
          <article className="feature-card">
            <span className="feature-icon">↕</span>
            <h3>Height strategy</h3>
            <p>Define sitting and standing ranges, memory presets, and safe transition habits.</p>
          </article>
          <article className="feature-card">
            <span className="feature-icon">◎</span>
            <h3>Accessory mapping</h3>
            <p>Match arms, trays, and power routing to each desk width and monitor count.</p>
          </article>
          <article className="feature-card">
            <span className="feature-icon">✓</span>
            <h3>Procurement handoff</h3>
            <p>Export a clear summary your operations team can use to quote and install.</p>
          </article>
        </div>
      </section>

      <section id="pricing" className="pricing-section section-shell">
        <div className="section-heading split">
          <div>
            <p className="eyebrow">Pricing</p>
            <h2>Pick the level of planning support you need.</h2>
          </div>
          <button
            className="ghost-button"
            data-action="pricing-toggle-comparison"
            type="button"
            aria-expanded={comparePlans}
            onClick={() => setComparePlans((visible) => !visible)}
          >
            {comparePlans ? "Hide comparison" : "Compare plans"}
          </button>
        </div>

        <div className="pricing-grid">
          {(Object.keys(plans) as PlanId[]).map((planId) => {
            const plan = plans[planId];
            return (
              <article className={`price-card ${plan.badge ? "highlight" : ""}`} key={planId}>
                {plan.badge ? <span className="badge">{plan.badge}</span> : null}
                <h3>{plan.label}</h3>
                <p>{plan.description}</p>
                <strong className="price">{plan.price}</strong>
                <ul>
                  {plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
                <button
                  className={plan.badge ? "primary-button" : "secondary-button"}
                  data-action={`select-plan-${planId}`}
                  type="button"
                  onClick={() => handleSelectPlan(planId)}
                >
                  Choose {plan.label}
                </button>
              </article>
            );
          })}
        </div>

        {comparePlans ? (
          <div className="comparison-panel" aria-live="polite">
            <div>
              <strong>Best for individuals</strong>
              <span>Starter gives a checklist and self-serve plan.</span>
            </div>
            <div>
              <strong>Best for growing teams</strong>
              <span>Team adds a consultation and rollout plan.</span>
            </div>
            <div>
              <strong>Best for complex offices</strong>
              <span>Enterprise adds multi-site audit support.</span>
            </div>
          </div>
        ) : null}
      </section>

      <section id="faq" className="faq-section section-shell">
        <div className="section-heading">
          <p className="eyebrow">FAQ</p>
          <h2>Questions teams ask before planning their desks.</h2>
        </div>
        <div className="faq-list">
          {faqItems.map((item, index) => {
            const isOpen = openFaq === index;
            return (
              <article className="faq-item" key={item.question}>
                <button
                  className="faq-question"
                  data-action={`faq-toggle-${index + 1}`}
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpenFaq(isOpen ? null : index)}
                >
                  <span>{item.question}</span>
                  <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
                </button>
                {isOpen ? <p>{item.answer}</p> : null}
              </article>
            );
          })}
        </div>
      </section>

      <section id="contact" className="contact-section section-shell">
        <div className="contact-card">
          <div>
            <p className="eyebrow">Next step</p>
            <h2>Request a consultation handoff.</h2>
            <p>
              The form is client-side for this handoff build. It validates required fields, confirms
              submission, and keeps selected plan or planner details in the message.
            </p>
          </div>

          <form className="contact-form" onSubmit={handleSubmit}>
            <label>
              Name
              <input
                name="name"
                type="text"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Alex Morgan"
              />
            </label>
            <label>
              Work email
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
                placeholder="alex@company.com"
              />
            </label>
            <label>
              Company
              <input
                name="company"
                type="text"
                value={form.company}
                onChange={(event) => setForm({ ...form, company: event.target.value })}
                placeholder="Company name"
              />
            </label>
            <label>
              Selected plan
              <select
                name="plan"
                value={form.plan}
                onChange={(event) => setForm({ ...form, plan: event.target.value })}
              >
                {Object.values(plans).map((plan) => (
                  <option key={plan.label} value={plan.label}>
                    {plan.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="full-span">
              Project details
              <textarea
                name="message"
                rows={5}
                value={form.message}
                onChange={(event) => setForm({ ...form, message: event.target.value })}
                placeholder="Tell us about the team, rooms, and timeline."
              />
            </label>
            <button
              className="primary-button full-span"
              data-action="contact-submit"
              type="submit"
            >
              Submit request
            </button>
            {formStatus === "sent" ? (
              <p className="form-success full-span" role="status">
                Thanks, {form.name || "there"}. Your consultation handoff is ready for review.
              </p>
            ) : null}
          </form>
        </div>
      </section>

      <footer className="footer">
        <span>© 2026 SwingDesk</span>
        <button
          className="nav-link"
          data-action="footer-back-to-top"
          type="button"
          onClick={() => scrollToSection("top")}
        >
          Back to top ↑
        </button>
      </footer>

      {demoOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setDemoOpen(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="demo-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              data-action="demo-close"
              type="button"
              aria-label="Close demo"
              onClick={() => setDemoOpen(false)}
            >
              ×
            </button>
            <p className="eyebrow">Demo</p>
            <h2 id="demo-title">How SwingDesk works</h2>
            <div className="video-placeholder">
              <span>▶</span>
              <p>Measure the space, choose a desk profile, add accessories, then export the plan.</p>
            </div>
            <button
              className="primary-button"
              data-action="demo-go-planner"
              type="button"
              onClick={() => {
                setDemoOpen(false);
                scrollToSection("planner");
              }}
            >
              Start planning
            </button>
          </section>
        </div>
      ) : null}

      {auditOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setAuditOpen(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              data-action="audit-close"
              type="button"
              aria-label="Close audit booking"
              onClick={() => setAuditOpen(false)}
            >
              ×
            </button>
            <p className="eyebrow">Workspace audit</p>
            <h2 id="audit-title">Book a workspace audit</h2>
            <p>
              Pick a 30-minute discovery call and bring room measurements, monitor counts, and any
              accessibility requirements. This demo opens the contact form with the right context.
            </p>
            <button
              className="primary-button"
              data-action="audit-prefill-contact"
              type="button"
              onClick={() => {
                setForm((current) => ({
                  ...current,
                  plan: "Enterprise",
                  message:
                    "I would like to book a workspace audit. We can share room measurements, monitor counts, and rollout requirements."
                }));
                setAuditOpen(false);
                scrollToSection("contact");
              }}
            >
              Continue to booking form
            </button>
          </section>
        </div>
      ) : null}

      {toast ? (
        <div className={`toast ${toast.tone}`} role="status">
          {toast.message}
        </div>
      ) : null}
    </main>
  );
}

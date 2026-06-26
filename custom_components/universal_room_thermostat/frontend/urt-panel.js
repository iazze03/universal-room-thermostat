class URTClimatePanel extends HTMLElement {
  set panel(panel) {
    this._panel = panel;
    this._config = panel?.config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  _state(entityId) {
    if (!entityId || !this._hass) return undefined;
    return this._hass.states[entityId];
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  _formatTemp(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "—";
    return `${numeric.toFixed(Math.abs(numeric % 1) < 0.05 ? 0 : 1)}°`;
  }

  _formatState(entityId, fallback = "—") {
    const state = this._state(entityId);
    if (!state || ["unknown", "unavailable"].includes(state.state)) return fallback;
    return state.state;
  }

  _roomStatus(room, climate) {
    const temp = this._state(room.temperature_sensor);
    const humidity = this._state(room.humidity_sensor);
    const presence = this._state(room.presence_entity);
    const request = this._state(room.cooling_request_entity);
    const current = climate?.attributes?.current_temperature ?? temp?.state;
    const target = climate?.attributes?.temperature;
    return {
      current: this._formatTemp(current),
      target: this._formatTemp(target),
      humidity: humidity ? `${Number(humidity.state).toFixed(0)}%` : "—",
      mode: climate?.state || "—",
      preset: climate?.attributes?.preset_mode || "—",
      presence: presence ? (presence.state === "on" ? "presente" : "mantenimento") : "standard",
      request: request ? request.state === "on" : false,
    };
  }

  _renderModeSelector() {
    const modeEntity = this._config.mode_entity;
    const controlEntity = this._config.control_enabled_entity;
    const mode = this._formatState(modeEntity, "—");
    const modeState = this._state(modeEntity);
    const modes = modeState?.attributes?.options || ["estate", "inverno", "spento", "auto"];
    const controlState = this._state(controlEntity);
    const controlEnabled = !controlEntity || !controlState || controlState.state === "on";
    return `
      <section class="hero">
        <div>
          <p class="eyebrow">Universal Room Thermostat</p>
          <h1>${this._escape(this._config.title || "Clima Casa")}</h1>
          <p class="subtitle">Una regia unica per valvole, canalizzato e split.</p>
        </div>
        <div class="mode-card ${controlEnabled ? "" : "disabled"}">
          <span>Controllo integrazione</span>
          <strong>${controlEnabled ? "Attivo" : "Disattivato"}</strong>
          ${
            controlEntity
              ? `<button class="master ${controlEnabled ? "active" : ""}" data-action="master-control" data-entity="${this._escape(controlEntity)}" data-value="${controlEnabled ? "off" : "on"}">
                  ${controlEnabled ? "Disattiva controllo clima" : "Riattiva controllo clima"}
                </button>`
              : `<p class="missing-helper">Helper controllo non configurato</p>`
          }
          <span>Modalità casa</span>
          <strong class="mode-value">${this._escape(mode)}</strong>
          <div class="mode-buttons">
            ${modes
              .map(
                (item) => `
                  <button class="${item === mode ? "active" : ""}" data-action="house-mode" data-entity="${this._escape(modeEntity)}" data-value="${this._escape(item)}">
                    ${this._escape(item)}
                  </button>`
              )
              .join("")}
          </div>
        </div>
      </section>`;
  }

  _renderRoom(room) {
    const climate = this._state(room.climate_entity);
    const status = this._roomStatus(room, climate);
    const hvacModes = climate?.attributes?.hvac_modes || ["off", "heat"];
    const presets = climate?.attributes?.preset_modes || ["comfort", "eco", "sleep", "away"];
    const target = Number(climate?.attributes?.temperature);
    const minus = Number.isFinite(target) ? target - 0.5 : 20;
    const plus = Number.isFinite(target) ? target + 0.5 : 20;

    return `
      <article class="room-card ${status.request ? "requesting" : ""}">
        <div class="room-top">
          <div>
            <h2>${this._escape(room.name)}</h2>
            <p>${this._escape(status.presence)} · ${this._escape(room.cooling_type)}</p>
          </div>
          <div class="request-dot" title="Richiesta raffrescamento"></div>
        </div>

        <div class="temperatures">
          <div>
            <span>attuale</span>
            <strong>${this._escape(status.current)}</strong>
          </div>
          <div>
            <span>target</span>
            <strong>${this._escape(status.target)}</strong>
          </div>
          <div>
            <span>umidità</span>
            <strong>${this._escape(status.humidity)}</strong>
          </div>
        </div>

        <div class="target-row">
          <button data-action="temperature" data-entity="${this._escape(room.climate_entity)}" data-value="${minus}">−</button>
          <span>${this._escape(status.mode)} · ${this._escape(status.preset)}</span>
          <button data-action="temperature" data-entity="${this._escape(room.climate_entity)}" data-value="${plus}">+</button>
        </div>

        <div class="chips">
          ${hvacModes
            .map(
              (mode) => `
                <button class="${mode === status.mode ? "active" : ""}" data-action="hvac" data-entity="${this._escape(room.climate_entity)}" data-value="${this._escape(mode)}">
                  ${this._escape(mode)}
                </button>`
            )
            .join("")}
        </div>

        <div class="chips presets">
          ${presets
            .map(
              (preset) => `
                <button class="${preset === status.preset ? "active" : ""}" data-action="preset" data-entity="${this._escape(room.climate_entity)}" data-value="${this._escape(preset)}">
                  ${this._escape(preset)}
                </button>`
            )
            .join("")}
        </div>
      </article>`;
  }

  _renderDiagnostics() {
    const diagnostics = this._config.diagnostics || {};
    const rows = [
      ["Richiesta freddo", diagnostics.cooling_requested],
      ["Stanza guida", diagnostics.active_room],
      ["Delta massimo", diagnostics.max_delta],
      ["Setpoint Daikin", diagnostics.requested_setpoint],
    ];
    return `
      <section class="diagnostics">
        <h2>Regia canalizzato</h2>
        <div class="diagnostic-grid">
          ${rows
            .map(([label, entity]) => {
              const state = this._state(entity);
              const value = state?.state && state.state !== "unknown" ? state.state : "—";
              return `
                <div>
                  <span>${this._escape(label)}</span>
                  <strong>${this._escape(value)}</strong>
                </div>`;
            })
            .join("")}
        </div>
      </section>`;
  }

  _render() {
    if (!this._hass || !this._config.rooms) return;
    if (!this._boundClick) {
      this._boundClick = (event) => this._handleClick(event);
      this.addEventListener("click", this._boundClick);
    }
    this.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background:
            radial-gradient(circle at top left, rgba(3, 169, 244, .22), transparent 34rem),
            radial-gradient(circle at bottom right, rgba(255, 152, 0, .16), transparent 30rem),
            var(--primary-background-color);
          color: var(--primary-text-color);
          box-sizing: border-box;
        }
        * { box-sizing: border-box; }
        .page {
          padding: 32px;
          max-width: 1480px;
          margin: 0 auto;
        }
        .hero {
          display: grid;
          grid-template-columns: 1fr minmax(280px, 420px);
          gap: 20px;
          align-items: stretch;
          margin-bottom: 22px;
        }
        .eyebrow {
          margin: 0 0 8px;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: .16em;
          font-size: 12px;
          font-weight: 700;
        }
        h1 {
          margin: 0;
          font-size: clamp(34px, 5vw, 64px);
          line-height: .95;
          letter-spacing: -.05em;
        }
        .subtitle {
          margin: 14px 0 0;
          color: var(--secondary-text-color);
          font-size: 18px;
        }
        .mode-card,
        .room-card,
        .diagnostics {
          border: 1px solid var(--divider-color);
          background: color-mix(in srgb, var(--card-background-color) 88%, transparent);
          border-radius: 28px;
          box-shadow: var(--ha-card-box-shadow, 0 18px 50px rgba(0,0,0,.14));
        }
        .mode-card {
          padding: 22px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          gap: 20px;
        }
        .mode-card span,
        .temperatures span,
        .diagnostic-grid span {
          color: var(--secondary-text-color);
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: .08em;
        }
        .mode-card strong {
          font-size: 34px;
          text-transform: capitalize;
        }
        .mode-card.disabled {
          border-color: var(--error-color);
        }
        .mode-card .master {
          width: 100%;
          background: var(--error-color);
          color: var(--text-primary-color);
          padding: 14px 18px;
        }
        .mode-card .master.active {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }
        .mode-card .mode-value {
          font-size: 24px;
        }
        .missing-helper {
          margin: 0;
          color: var(--error-color);
        }
        .mode-buttons,
        .chips {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        button {
          border: 0;
          border-radius: 999px;
          padding: 10px 14px;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font: inherit;
          font-weight: 700;
        }
        button.active {
          background: var(--primary-color);
          color: var(--text-primary-color);
        }
        .rooms {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
          gap: 18px;
        }
        .room-card {
          padding: 20px;
          position: relative;
          overflow: hidden;
        }
        .room-card.requesting {
          border-color: var(--primary-color);
        }
        .room-top,
        .target-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
        }
        .room-top h2 {
          margin: 0;
          font-size: 24px;
          letter-spacing: -.03em;
        }
        .room-top p {
          margin: 4px 0 0;
          color: var(--secondary-text-color);
        }
        .request-dot {
          width: 14px;
          height: 14px;
          border-radius: 99px;
          background: var(--disabled-text-color);
        }
        .requesting .request-dot {
          background: var(--primary-color);
          box-shadow: 0 0 0 8px color-mix(in srgb, var(--primary-color) 18%, transparent);
        }
        .temperatures {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 10px;
          margin: 22px 0;
        }
        .temperatures div,
        .diagnostic-grid div {
          padding: 14px;
          border-radius: 18px;
          background: var(--secondary-background-color);
        }
        .temperatures strong {
          display: block;
          margin-top: 6px;
          font-size: 30px;
          letter-spacing: -.05em;
        }
        .target-row {
          margin-bottom: 14px;
        }
        .target-row button {
          width: 46px;
          height: 46px;
          padding: 0;
          font-size: 24px;
        }
        .target-row span {
          color: var(--secondary-text-color);
          text-transform: uppercase;
          font-size: 12px;
          letter-spacing: .08em;
        }
        .presets {
          margin-top: 8px;
        }
        .diagnostics {
          padding: 20px;
          margin-top: 18px;
        }
        .diagnostics h2 {
          margin: 0 0 14px;
        }
        .diagnostic-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 12px;
        }
        .diagnostic-grid strong {
          display: block;
          margin-top: 6px;
          font-size: 22px;
        }
        @media (max-width: 760px) {
          .page { padding: 18px; }
          .hero { grid-template-columns: 1fr; }
        }
      </style>
      <main class="page">
        ${this._renderModeSelector()}
        <section class="rooms">
          ${this._config.rooms.map((room) => this._renderRoom(room)).join("")}
        </section>
        ${this._renderDiagnostics()}
      </main>
    `;
  }

  _handleClick(event) {
    const button = event.target.closest("button[data-action]");
    if (!button || !this._hass) return;
    const entityId = button.dataset.entity;
    const value = button.dataset.value;
    if (!entityId || value == null) return;
    if (button.dataset.action === "house-mode") {
      this._hass.callService("input_select", "select_option", {
        entity_id: entityId,
        option: value,
      });
      return;
    }
    if (button.dataset.action === "master-control") {
      this._hass.callService("input_boolean", button.dataset.value === "on" ? "turn_on" : "turn_off", {
        entity_id: entityId,
      });
      return;
    }
    if (button.dataset.action === "temperature") {
      this._hass.callService("climate", "set_temperature", {
        entity_id: entityId,
        temperature: Number(value),
      });
      return;
    }
    if (button.dataset.action === "hvac") {
      this._hass.callService("climate", "set_hvac_mode", {
        entity_id: entityId,
        hvac_mode: value,
      });
      return;
    }
    if (button.dataset.action === "preset") {
      this._hass.callService("climate", "set_preset_mode", {
        entity_id: entityId,
        preset_mode: value,
      });
    }
  }
}

customElements.define("urt-climate-panel", URTClimatePanel);

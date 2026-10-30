/*
 * Heizplan-Karte für Home Assistant – Wochenzeitplan im Tado-Stil.
 * Wird von der Integration "heating_schedule" automatisch geladen.
 */
const CARD_VERSION = "1.0.0";
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DAY_SHORT = { mon: "Mo", tue: "Di", wed: "Mi", thu: "Do", fri: "Fr", sat: "Sa", sun: "So" };
const DAY_LONG = {
  mon: "Montag", tue: "Dienstag", wed: "Mittwoch", thu: "Donnerstag",
  fri: "Freitag", sat: "Samstag", sun: "Sonntag",
};
const COPY_TARGETS = [
  { label: "Mo–Fr", days: ["mon", "tue", "wed", "thu", "fri"] },
  { label: "Sa + So", days: ["sat", "sun"] },
  { label: "Alle Tage", days: DAYS },
];

const toMin = (s) => {
  const [h, m] = String(s).split(":").map(Number);
  return h * 60 + m;
};
const fmtMin = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const num = (v) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
};
const fmtTemp = (t) =>
  t == null ? "–" : `${t.toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}°`;
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** Temperatur -> Farbe: kühl blau, warm orange/rot (wie Tado). */
function tempColor(t) {
  if (t == null) return "var(--hs-off)";
  const c = Math.min(1, Math.max(0, (t - 15) / 9));
  const hue = 205 - c * 190;
  return `hsl(${hue.toFixed(0)} 80% ${c < 0.5 ? 50 : 54}%)`;
}

function todayKey() {
  return DAYS[(new Date().getDay() + 6) % 7];
}

class HeatingScheduleCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._day = null;
    this._editing = false;
    this._draft = null;
    this._pending = {};
    this._timers = {};
    this._sig = null;
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.schedule && hass.states[id].attributes.zone_id,
    );
    return { entity: entity || "" };
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entity", required: true, selector: { entity: { domain: "sensor", integration: "heating_schedule" } } },
        { name: "title", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "show_presets", selector: { boolean: {} } },
            { name: "show_mode", selector: { boolean: {} } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          entity: "Heizplan-Sensor (Solltemperatur)",
          title: "Titel (optional)",
          show_presets: "Temperatur-Presets anzeigen",
          show_mode: "Modus-Auswahl anzeigen",
        })[s.name],
    };
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("Bitte 'entity' angeben (Sensor 'Solltemperatur' einer Heizzone).");
    this._config = { show_presets: true, show_mode: true, ...config };
    this._sig = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._signature();
    if (sig === this._sig) return;
    this._sig = sig;
    this._clearSettledPending();
    if (!this._editing) this._render();
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ------------------------------------------------------------------ Daten
  _signature() {
    const st = this._hass?.states[this._config?.entity];
    if (!st) return "missing";
    const a = st.attributes;
    const ids = [
      a.mode_entity,
      ...(a.climate_entities || []),
      ...(a.presets || []).map((p) => p.entity_id),
    ].filter(Boolean);
    return [st.last_updated, ...ids.map((id) => this._hass.states[id]?.last_updated)].join("|");
  }

  _data() {
    const hass = this._hass;
    const st = hass.states[this._config.entity];
    if (!st) return null;
    const a = st.attributes;
    const presets = (a.presets || []).map((p) => {
      const ent = p.entity_id && hass.states[p.entity_id];
      const temp = this._pending[p.key] ?? num(ent?.state) ?? p.temperature;
      return {
        ...p,
        temperature: temp,
        min: num(ent?.attributes.min) ?? 5,
        max: num(ent?.attributes.max) ?? 30,
        step: num(ent?.attributes.step) ?? 0.5,
      };
    });
    const pmap = Object.fromEntries(presets.map((p) => [p.key, p]));
    const climate = (a.climate_entities || []).map((id) => hass.states[id]).find(Boolean);
    const modeEnt = a.mode_entity && hass.states[a.mode_entity];
    return {
      st, a, presets, pmap, climate,
      target: num(st.state),
      mode: modeEnt?.state ?? a.mode,
      modeOptions: modeEnt?.attributes.options || [],
      schedule: a.schedule || {},
    };
  }

  _clearSettledPending() {
    if (!this._hass) return;
    const st = this._hass.states[this._config?.entity];
    for (const p of st?.attributes.presets || []) {
      if (this._pending[p.key] == null || this._timers[p.key]) continue;
      if (num(this._hass.states[p.entity_id]?.state) === this._pending[p.key]) delete this._pending[p.key];
    }
  }

  // ------------------------------------------------------------- Rendering
  _render() {
    if (!this._config || !this._hass) return;
    const d = this._data();
    if (!d) {
      this.shadowRoot.innerHTML = `${STYLE}<ha-card><div class="warn">Entität <b>${esc(this._config.entity)}</b> nicht gefunden.</div></ha-card>`;
      return;
    }
    if (!this._day) this._day = todayKey();
    const blocks = this._editing ? this._draft : d.schedule[this._day] || [];

    this.shadowRoot.innerHTML = `
      ${STYLE}
      <ha-card>
        ${this._headerHTML(d)}
        ${this._config.show_mode && d.modeOptions.length ? this._modeHTML(d) : ""}
        ${this._config.show_presets ? this._presetsHTML(d) : ""}
        <div class="section">
          <div class="section-head">
            <span>Zeitplan</span>
            ${this._editing ? "" : `<button class="link" data-act="edit"><ha-icon icon="mdi:pencil"></ha-icon>Bearbeiten</button>`}
          </div>
          <div class="days">
            ${DAYS.map(
              (day) => `<button class="day ${day === this._day ? "sel" : ""} ${day === todayKey() ? "today" : ""}"
                data-act="day" data-day="${day}" ${this._editing ? "disabled" : ""}>${DAY_SHORT[day]}</button>`,
            ).join("")}
          </div>
          <div class="timeline-wrap">${this._timelineHTML(blocks, d.pmap)}</div>
          ${this._editing ? this._editorHTML(blocks, d) : this._blockListHTML(blocks, d)}
        </div>
      </ha-card>`;
  }

  _headerHTML(d) {
    const room = num(d.climate?.attributes.current_temperature);
    const hum = num(d.climate?.attributes.current_humidity);
    const heating = d.climate?.attributes.hvac_action === "heating";
    const off = d.target == null;
    const color = tempColor(d.target);
    const preset = d.pmap[d.a.current_preset];
    let next = "";
    if (d.a.next_change && d.pmap[d.a.next_preset]) {
      const dt = new Date(d.a.next_change);
      const sameDay = dt.toDateString() === new Date().toDateString();
      const when = `${sameDay ? "" : DAY_SHORT[DAYS[(dt.getDay() + 6) % 7]] + " "}${fmtMin(dt.getHours() * 60 + dt.getMinutes())}`;
      const np = d.pmap[d.a.next_preset];
      next = `Ab ${when}: ${esc(np.name)} ${fmtTemp(np.temperature)}`;
    } else if (d.mode && d.mode !== "Zeitplan") {
      next = d.mode === "Aus" ? "Zeitplan pausiert" : "Manuell – Zeitplan pausiert";
    }
    return `
      <div class="hero" style="--hero:${color}">
        <div class="hero-top">
          <div class="zone">${esc(this._config.title || d.a.zone_name || "Heizung")}</div>
          ${heating ? `<div class="badge"><ha-icon icon="mdi:fire"></ha-icon>heizt</div>` : ""}
        </div>
        <div class="hero-main">
          <div class="target">${off ? "AUS" : fmtTemp(d.target)}</div>
          <div class="hero-meta">
            ${preset && !off ? `<div class="preset-name">${esc(preset.name)}</div>` : ""}
            ${next ? `<div class="next">${next}</div>` : ""}
          </div>
        </div>
        <div class="hero-room">
          ${room != null ? `<span><ha-icon icon="mdi:thermometer"></ha-icon>Raum ${fmtTemp(room)}</span>` : ""}
          ${hum != null ? `<span><ha-icon icon="mdi:water-percent"></ha-icon>${hum.toFixed(0)} %</span>` : ""}
        </div>
      </div>`;
  }

  _modeHTML(d) {
    return `<div class="chips">${d.modeOptions
      .map((opt) => {
        const icon = opt === "Zeitplan" ? "mdi:calendar-clock" : opt === "Aus" ? "mdi:power" : "";
        return `<button class="chip ${opt === d.mode ? "sel" : ""}" data-act="mode" data-opt="${esc(opt)}">
          ${icon ? `<ha-icon icon="${icon}"></ha-icon>` : ""}${esc(opt)}</button>`;
      })
      .join("")}</div>`;
  }

  _presetsHTML(d) {
    return `<div class="section">
      <div class="section-head"><span>Temperaturen</span></div>
      <div class="presets">${d.presets
        .map(
          (p) => `<div class="preset">
            <span class="dot" style="background:${tempColor(p.temperature)}"></span>
            <span class="pname">${esc(p.name)}</span>
            <button class="round" data-act="dec" data-key="${esc(p.key)}" aria-label="kälter"><ha-icon icon="mdi:minus"></ha-icon></button>
            <span class="pval">${fmtTemp(p.temperature)}</span>
            <button class="round" data-act="inc" data-key="${esc(p.key)}" aria-label="wärmer"><ha-icon icon="mdi:plus"></ha-icon></button>
          </div>`,
        )
        .join("")}</div></div>`;
  }

  _segments(blocks) {
    const sorted = [...blocks].sort((x, y) => toMin(x.start) - toMin(y.start));
    return sorted.map((b, i) => ({
      ...b,
      from: i === 0 ? 0 : toMin(b.start),
      to: i + 1 < sorted.length ? toMin(sorted[i + 1].start) : 1440,
    }));
  }

  _timelineHTML(blocks, pmap) {
    const segs = this._segments(blocks);
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const isToday = this._day === todayKey();
    return `
      <div class="timeline">
        ${segs
          .map((s) => {
            const p = pmap[s.preset];
            const w = ((s.to - s.from) / 1440) * 100;
            return `<div class="seg" style="left:${(s.from / 1440) * 100}%;width:${w}%;background:${tempColor(p?.temperature)}"
              title="${fmtMin(s.from)}–${fmtMin(s.to)} ${esc(p?.name)}">${w > 9 ? `<span>${fmtTemp(p?.temperature)}</span>` : ""}</div>`;
          })
          .join("")}
        ${isToday ? `<div class="now" style="left:${(nowMin / 1440) * 100}%"></div>` : ""}
      </div>
      <div class="ticks">${[0, 6, 12, 18, 24].map((h) => `<span>${h}</span>`).join("")}</div>`;
  }

  _blockListHTML(blocks, d) {
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    const isToday = this._day === todayKey();
    return `<div class="blocks">${this._segments(blocks)
      .map((s) => {
        const p = d.pmap[s.preset];
        const active = isToday && nowMin >= s.from && nowMin < s.to;
        return `<div class="block ${active ? "active" : ""}" data-act="edit">
          <span class="bar" style="background:${tempColor(p?.temperature)}"></span>
          <span class="btime">${fmtMin(s.from)} – ${s.to === 1440 ? "24:00" : fmtMin(s.to)}</span>
          <span class="bname">${esc(p?.name ?? s.preset)}</span>
          <span class="btemp">${fmtTemp(p?.temperature)}</span>
        </div>`;
      })
      .join("")}</div>`;
  }

  _editorHTML(blocks, d) {
    const options = (sel) =>
      d.presets.map((p) => `<option value="${esc(p.key)}" ${p.key === sel ? "selected" : ""}>${esc(p.name)} · ${fmtTemp(p.temperature)}</option>`).join("");
    return `
      <div class="editor">
        <div class="edit-title">${DAY_LONG[this._day]} bearbeiten</div>
        ${blocks
          .map(
            (b, i) => `<div class="erow">
              <span class="bar" style="background:${tempColor(d.pmap[b.preset]?.temperature)}"></span>
              <input type="time" step="900" value="${esc(b.start)}" data-idx="${i}" data-field="start" ${i === 0 ? "disabled" : ""}>
              <select data-idx="${i}" data-field="preset">${options(b.preset)}</select>
              ${i === 0 ? `<span class="spacer"></span>` : `<button class="round danger" data-act="del" data-idx="${i}" aria-label="Block löschen"><ha-icon icon="mdi:delete-outline"></ha-icon></button>`}
            </div>`,
          )
          .join("")}
        <button class="add" data-act="add"><ha-icon icon="mdi:plus"></ha-icon>Zeitblock hinzufügen</button>
        <div class="copy">
          <span>Speichern für:</span>
          ${COPY_TARGETS.map((t, i) => `<button class="chip small" data-act="copy" data-i="${i}">${t.label}</button>`).join("")}
        </div>
        <div class="actions">
          <button class="btn ghost" data-act="cancel">Abbrechen</button>
          <button class="btn primary" data-act="save">Speichern</button>
        </div>
        ${this._error ? `<div class="warn">${esc(this._error)}</div>` : ""}
      </div>`;
  }

  // ---------------------------------------------------------------- Events
  _onClick(e) {
    const el = e.target.closest("[data-act]");
    if (!el || el.disabled) return;
    const act = el.dataset.act;
    const d = this._data();
    if (!d) return;

    switch (act) {
      case "day":
        this._day = el.dataset.day;
        this._render();
        break;
      case "mode":
        this._hass.callService("select", "select_option", { entity_id: d.a.mode_entity, option: el.dataset.opt });
        break;
      case "inc":
      case "dec":
        this._stepPreset(d, el.dataset.key, act === "inc" ? 1 : -1);
        break;
      case "edit":
        this._draft = (d.schedule[this._day] || []).map((b) => ({ ...b }));
        if (!this._draft.length) this._draft = [{ start: "00:00", preset: d.presets[0]?.key }];
        this._editing = true;
        this._error = null;
        this._render();
        break;
      case "cancel":
        this._editing = false;
        this._draft = null;
        this._render();
        break;
      case "add":
        this._addBlock(d);
        this._render();
        break;
      case "del":
        this._draft.splice(Number(el.dataset.idx), 1);
        this._render();
        break;
      case "save":
        this._save(d, [this._day]);
        break;
      case "copy":
        this._save(d, [...new Set([this._day, ...COPY_TARGETS[Number(el.dataset.i)].days])]);
        break;
    }
  }

  _onChange(e) {
    const el = e.target;
    if (!this._editing || el.dataset.idx == null) return;
    const block = this._draft[Number(el.dataset.idx)];
    if (!block) return;
    if (el.dataset.field === "start" && el.value) block.start = el.value.slice(0, 5);
    if (el.dataset.field === "preset") {
      block.preset = el.value;
      const bar = el.parentElement.querySelector(".bar");
      if (bar) bar.style.background = tempColor(this._data().pmap[el.value]?.temperature);
    }
    // nur die Zeitleiste neu zeichnen, damit der Fokus im Eingabefeld bleibt
    const wrap = this.shadowRoot.querySelector(".timeline-wrap");
    if (wrap) wrap.innerHTML = this._timelineHTML(this._draft, this._data().pmap);
  }

  _stepPreset(d, key, dir) {
    const p = d.pmap[key];
    if (!p || p.temperature == null) return;
    const value = Math.round(Math.min(p.max, Math.max(p.min, p.temperature + dir * p.step)) * 10) / 10;
    this._pending[key] = value;
    this._render();
    clearTimeout(this._timers[key]);
    this._timers[key] = setTimeout(async () => {
      delete this._timers[key];
      try {
        await this._hass.callService("number", "set_value", { entity_id: p.entity_id, value });
      } catch (err) {
        delete this._pending[key];
        this._render();
      }
    }, 600);
  }

  _addBlock(d) {
    const segs = this._segments(this._draft);
    const longest = segs.reduce((a, b) => (b.to - b.from > a.to - a.from ? b : a), segs[0]);
    const mid = Math.round((longest.from + longest.to) / 2 / 15) * 15;
    const start = Math.min(Math.max(mid, longest.from + 15), 1425);
    const preset = d.presets.find((p) => p.key !== longest.preset)?.key ?? longest.preset;
    this._draft.push({ start: fmtMin(start), preset });
    this._draft.sort((a, b) => toMin(a.start) - toMin(b.start));
  }

  async _save(d, days) {
    const blocks = [...this._draft]
      .sort((a, b) => toMin(a.start) - toMin(b.start))
      .map((b, i) => ({ start: i === 0 ? "00:00" : b.start, preset: b.preset }));
    try {
      await this._hass.callService("heating_schedule", "set_schedule", { zone_id: d.a.zone_id, days, blocks });
      this._editing = false;
      this._draft = null;
      this._error = null;
    } catch (err) {
      this._error = `Speichern fehlgeschlagen: ${err.message || err}`;
    }
    this._render();
  }
}

const STYLE = `<style>
  :host { --hs-off: var(--disabled-text-color, #9e9e9e); --hs-radius: 14px; }
  ha-card { overflow: hidden; padding-bottom: 8px; }
  button { font: inherit; color: inherit; cursor: pointer; border: none; background: none; }
  ha-icon { --mdc-icon-size: 18px; }
  .warn { padding: 12px 16px; color: var(--error-color, #db4437); }

  .hero { background: linear-gradient(135deg, var(--hero), color-mix(in srgb, var(--hero) 70%, #000));
    color: #fff; padding: 16px 18px 14px; transition: background .4s; }
  .hero-top { display: flex; justify-content: space-between; align-items: center; }
  .zone { font-size: 1.05rem; font-weight: 600; letter-spacing: .2px; opacity: .95; }
  .badge { display: flex; align-items: center; gap: 4px; font-size: .8rem; background: rgba(255,255,255,.22);
    padding: 3px 9px; border-radius: 99px; }
  .hero-main { display: flex; align-items: flex-end; gap: 14px; margin-top: 6px; }
  .target { font-size: 3.4rem; font-weight: 300; line-height: 1; letter-spacing: -1px; }
  .hero-meta { padding-bottom: 6px; display: flex; flex-direction: column; gap: 2px; }
  .preset-name { font-weight: 600; }
  .next { font-size: .85rem; opacity: .9; }
  .hero-room { display: flex; gap: 14px; margin-top: 10px; font-size: .85rem; opacity: .92; }
  .hero-room span { display: flex; align-items: center; gap: 3px; }

  .chips { display: flex; gap: 8px; padding: 12px 16px 0; overflow-x: auto; scrollbar-width: none; }
  .chip { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; padding: 6px 12px; border-radius: 99px;
    border: 1px solid var(--divider-color); font-size: .85rem; }
  .chip.sel { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip.small { padding: 4px 10px; font-size: .8rem; }

  .section { padding: 12px 16px 0; }
  .section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;
    font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .6px; color: var(--secondary-text-color); }
  .link { display: inline-flex; align-items: center; gap: 4px; color: var(--primary-color); text-transform: none;
    letter-spacing: 0; font-weight: 500; font-size: .9rem; }

  .presets { display: grid; gap: 6px; }
  .preset { display: grid; grid-template-columns: 12px 1fr 34px 62px 34px; align-items: center; gap: 8px;
    padding: 6px 4px 6px 10px; border-radius: 12px; background: var(--secondary-background-color, rgba(127,127,127,.08)); }
  .dot { width: 12px; height: 12px; border-radius: 50%; }
  .pname { font-weight: 500; }
  .pval { text-align: center; font-size: 1.15rem; font-variant-numeric: tabular-nums; }
  .round { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
    background: var(--card-background-color, var(--ha-card-background, #fff)); border: 1px solid var(--divider-color); }
  .round:active { transform: scale(.94); }
  .round.danger { color: var(--error-color, #db4437); }

  .days { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 12px; }
  .day { padding: 7px 0; border-radius: 10px; font-weight: 500; font-size: .9rem; position: relative; }
  .day.today::after { content: ""; position: absolute; left: 50%; bottom: 2px; width: 4px; height: 4px;
    margin-left: -2px; border-radius: 50%; background: var(--primary-color); }
  .day.sel { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .day.sel.today::after { background: var(--text-primary-color, #fff); }
  .day:disabled { opacity: .45; cursor: default; }
  .day.sel:disabled { opacity: 1; }

  .timeline { position: relative; height: 38px; border-radius: 10px; overflow: hidden;
    background: var(--secondary-background-color, rgba(127,127,127,.1)); }
  .seg { position: absolute; top: 0; bottom: 0; display: grid; place-items: center; color: #fff;
    font-size: .78rem; font-weight: 600; border-right: 2px solid var(--card-background-color, var(--ha-card-background, #fff));
    box-sizing: border-box; transition: left .2s, width .2s; }
  .seg span { text-shadow: 0 1px 2px rgba(0,0,0,.25); }
  .now { position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--primary-text-color); margin-left: -1px; }
  .now::before { content: ""; position: absolute; top: 0; left: -3px; width: 8px; height: 8px; border-radius: 50%;
    background: var(--primary-text-color); }
  .ticks { display: flex; justify-content: space-between; font-size: .72rem; color: var(--secondary-text-color);
    margin: 4px 1px 10px; font-variant-numeric: tabular-nums; }

  .blocks { display: grid; gap: 2px; }
  .block { display: grid; grid-template-columns: 4px 112px 1fr auto; align-items: center; gap: 12px;
    padding: 9px 8px 9px 0; border-radius: 10px; cursor: pointer; }
  .block:hover { background: var(--secondary-background-color, rgba(127,127,127,.08)); }
  .block.active { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
  .bar { width: 4px; height: 26px; border-radius: 2px; }
  .btime { font-variant-numeric: tabular-nums; color: var(--secondary-text-color); font-size: .9rem; }
  .bname { font-weight: 500; }
  .btemp { font-variant-numeric: tabular-nums; font-weight: 600; }

  .editor { display: grid; gap: 8px; }
  .edit-title { font-weight: 600; margin-bottom: 2px; }
  .erow { display: grid; grid-template-columns: 4px 104px 1fr 34px; align-items: center; gap: 8px; }
  .erow input, .erow select { font: inherit; color: var(--primary-text-color); padding: 7px 8px; border-radius: 9px;
    border: 1px solid var(--divider-color); background: var(--card-background-color, var(--ha-card-background, #fff));
    min-width: 0; color-scheme: light dark; }
  .erow input:disabled { opacity: .6; }
  .add { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 9px; border-radius: 10px;
    border: 1px dashed var(--divider-color); color: var(--primary-color); font-weight: 500; }
  .copy { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: .85rem; color: var(--secondary-text-color); }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
  .btn { padding: 8px 18px; border-radius: 99px; font-weight: 600; }
  .btn.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn.ghost { border: 1px solid var(--divider-color); }
</style>`;

if (!customElements.get("heating-schedule-card")) {
  customElements.define("heating-schedule-card", HeatingScheduleCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "heating-schedule-card",
    name: "Heizplan",
    description: "Wochenzeitplan und Temperatur-Presets im Tado-Stil",
    preview: true,
    documentationURL: "https://github.com/Tillhnz/HA-Heatingtimes",
  });
  console.info(`%c HEIZPLAN-KARTE %c ${CARD_VERSION} `, "background:#f59e0b;color:#fff;font-weight:700", "background:#333;color:#fff");
}

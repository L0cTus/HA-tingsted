// Tingsted-kort for Home Assistant: søk, lån ut, levert tilbake, legg i kasse og siste endringer.
// Lastes automatisk av integrasjonen. Bruk:  type: custom:tingsted-card
// Valg:  title, sections: [search, lent, add, recent], config_entry_id (hvis du har flere husstander)
(() => {
  const SECTIONS = ["search", "lent", "add", "recent"];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ago = (t) => {
    if (!t) return "";
    const d = Date.now() / 1000 - t;
    if (d < 90) return "akkurat nå";
    if (d < 3600) return `for ${Math.floor(d / 60)} min siden`;
    if (d < 86400) return `for ${Math.floor(d / 3600)} t siden`;
    const days = Math.floor(d / 86400);
    return days === 1 ? "i går" : days < 60 ? `for ${days} dager siden` : new Date(t * 1000).toLocaleDateString("no-NO");
  };
  const day = (t) => (t ? new Date(t * 1000).toLocaleDateString("no-NO") : "");

  class TingstedCard extends HTMLElement {
    setConfig(config) {
      this._config = { sections: SECTIONS, ...config };
      this._results = null;
      this._speech = "";
      this._recent = null;
      this._busy = new Set();
      this._lendOpen = null;
      if (this.shadowRoot) this._build();
    }

    static getStubConfig() { return {}; }
    getCardSize() { return 8; }

    set hass(hass) {
      const first = !this._hass;
      this._hass = hass;
      if (!this.shadowRoot) { this.attachShadow({ mode: "open" }); this._build(); }
      const ents = this._entities();
      const sig = JSON.stringify(["lent", "items", "boxes", "lent_overdue", "last_event", "total_value"].map((k) => {
        const st = ents[k] && hass.states[ents[k]]; return st ? st.last_updated + st.state : "";
      }));
      if (sig !== this._sig) {
        this._sig = sig;
        this._renderStats();
        this._renderLent();
        if (!first && this._has("recent")) this._loadRecent();
      }
      if (first && this._has("recent")) this._loadRecent();
    }

    _has(s) { return (this._config.sections || SECTIONS).includes(s); }

    // Finn Tingsted-enhetene (for riktig husstand hvis config_entry_id er satt)
    _entities() {
      const out = {};
      const want = this._config.config_entry_id;
      for (const [id, e] of Object.entries(this._hass.entities || {})) {
        if (e.platform !== "tingsted") continue;
        if (want) {
          const dev = this._hass.devices && this._hass.devices[e.device_id];
          if (!dev || !(dev.config_entries || []).includes(want)) continue;
        }
        const key = e.translation_key || (id.split(".")[1] || "");
        if (key && !out[key]) out[key] = id;
        if (!out._device && e.device_id) out._device = e.device_id;
      }
      return out;
    }

    _state(key) {
      const id = this._entities()[key];
      return id ? this._hass.states[id] : undefined;
    }

    async _call(service, data, response = false) {
      const service_data = { ...data };
      if (this._config.config_entry_id) service_data.config_entry_id = this._config.config_entry_id;
      const res = await this._hass.callWS({ type: "call_service", domain: "tingsted", service, service_data, return_response: response });
      return response ? res.response : res;
    }

    _build() {
      const title = this._config.title || "";
      this.shadowRoot.innerHTML = `
        <style>
          :host { --ts-gold: var(--tingsted-accent, #c9975f); }
          ha-card { padding: 16px; }
          .head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
          .title { font-size: 1.25rem; font-weight: 500; display: flex; align-items: center; gap: 8px; }
          .title ha-icon { color: var(--ts-gold); }
          .chips { display: flex; gap: 6px; flex-wrap: wrap; }
          .chip { padding: 3px 10px; border-radius: 99px; background: var(--secondary-background-color); font-size: .85rem; white-space: nowrap; }
          .chip b { font-weight: 600; }
          .chip.warn { background: color-mix(in srgb, var(--error-color, #db4437) 18%, transparent); color: var(--error-color, #db4437); }
          .sec { margin-top: 16px; }
          .sec h3 { margin: 0 0 8px; font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color); }
          form.search { display: flex; gap: 8px; }
          input, textarea { font: inherit; color: var(--primary-text-color); background: var(--card-background-color, var(--ha-card-background));
            border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px 12px; width: 100%; box-sizing: border-box; }
          input:focus, textarea:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
          button { font: inherit; font-weight: 500; border: 0; border-radius: 10px; padding: 9px 14px; cursor: pointer;
            background: var(--primary-color); color: var(--text-primary-color, #fff); white-space: nowrap; }
          button.ghost { background: var(--secondary-background-color); color: var(--primary-text-color); }
          button.small { padding: 6px 10px; font-size: .85rem; }
          button[disabled] { opacity: .5; cursor: default; }
          .speech { margin: 10px 0 4px; padding: 10px 12px; border-radius: 10px; background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
          ul { list-style: none; margin: 0; padding: 0; }
          li.row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-bottom: 1px solid var(--divider-color); }
          li.row:last-child { border-bottom: 0; }
          .grow { flex: 1; min-width: 0; }
          .name { font-weight: 500; }
          .sub { color: var(--secondary-text-color); font-size: .85rem; overflow: hidden; text-overflow: ellipsis; }
          .late { color: var(--error-color, #db4437); font-weight: 500; }
          .badge { font-size: .75rem; padding: 1px 7px; border-radius: 99px; background: color-mix(in srgb, var(--warning-color, #ffa600) 20%, transparent); }
          .acts { display: flex; gap: 6px; flex: none; }
          .lendform { display: flex; gap: 6px; padding: 0 0 10px; }
          .lendform input { padding: 7px 10px; }
          .muted { color: var(--secondary-text-color); font-size: .9rem; }
          .add { display: grid; gap: 8px; }
          .add textarea { min-height: 64px; resize: vertical; }
          .msg { font-size: .9rem; margin-top: 6px; color: var(--secondary-text-color); }
          a { color: var(--primary-color); }
        </style>
        <ha-card>
          <div class="head">
            <div class="title"><ha-icon icon="mdi:package-variant-closed"></ha-icon><span id="title">${esc(title || "Tingsted")}</span></div>
            <div class="chips" id="chips"></div>
          </div>
          ${this._has("search") ? `<div class="sec">
            <form class="search" id="sform"><input id="q" type="search" placeholder="Hva leter du etter?" autocomplete="off" enterkeyhint="search"><button id="sbtn">Søk</button></form>
            <div id="sres"></div></div>` : ""}
          ${this._has("lent") ? `<div class="sec"><h3>Utlånt</h3><div id="lent"></div></div>` : ""}
          ${this._has("add") ? `<div class="sec"><h3>Legg i kasse</h3>
            <form class="add" id="aform"><input id="abox" placeholder="Kasse, f.eks. B3" autocomplete="off">
              <textarea id="aitems" placeholder="Én ting per linje. «skruer x50» gir antall 50."></textarea><button>Legg til</button></form>
            <div class="msg" id="amsg"></div></div>` : ""}
          ${this._has("recent") ? `<div class="sec"><h3>Siste endringer</h3><div id="recent"><div class="muted">Henter …</div></div></div>` : ""}
        </ha-card>`;
      const r = this.shadowRoot;
      r.getElementById("sform")?.addEventListener("submit", (e) => { e.preventDefault(); this._search(); });
      r.getElementById("aform")?.addEventListener("submit", (e) => { e.preventDefault(); this._add(); });
      r.addEventListener("click", (e) => this._click(e));
      r.addEventListener("submit", (e) => {
        const f = e.target.closest("form.lendform");
        if (f) { e.preventDefault(); this._lend(Number(f.dataset.id), f.querySelector("[name=to]").value, f.querySelector("[name=due]").value); }
      });
      if (this._hass) { this._renderStats(); this._renderLent(); this._renderResults(); }
    }

    _renderStats() {
      const el = this.shadowRoot?.getElementById("chips");
      if (!el || !this._hass) return;
      const v = (k) => this._state(k)?.state;
      const over = Number(v("lent_overdue") || 0) || (this._state("overdue")?.state === "on" ? 1 : 0);
      const chips = [["Kasser", v("boxes")], ["Ting", v("items")], ["Utlånt", v("lent")]]
        .filter(([, n]) => n !== undefined && n !== "unavailable")
        .map(([l, n]) => `<span class="chip ${l === "Utlånt" && over ? "warn" : ""}">${l} <b>${esc(n)}</b></span>`);
      el.innerHTML = chips.join("");
      const dev = this._entities()._device;
      const name = dev && this._hass.devices?.[dev]?.name;
      if (!this._config.title && name) this.shadowRoot.getElementById("title").textContent = name;
    }

    _itemRow(it, where, lentTo, due, url) {
      const late = due && due < Date.now() / 1000;
      const lendOpen = this._lendOpen === it.id;
      const busy = this._busy.has(it.id);
      return `<li class="row">
          <div class="grow"><div class="name">${esc(it.name)}${it.qty && it.qty !== 1 ? ` <span class="muted">×${esc(it.qty)}</span>` : ""}
            ${lentTo ? ` <span class="badge">hos ${esc(lentTo)}</span>` : ""}</div>
            <div class="sub">${esc(where || "")}${due ? ` · <span class="${late ? "late" : ""}">${late ? "skulle vært tilbake" : "tilbake innen"} ${day(due)}</span>` : ""}</div></div>
          <div class="acts">
            ${lentTo ? `<button class="small" data-act="return" data-id="${it.id}" ${busy ? "disabled" : ""}>Levert</button>`
                     : (it.id ? `<button class="small ghost" data-act="lendopen" data-id="${it.id}">Lån ut</button>` : "")}
            ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener"><button class="small ghost" tabindex="-1">Åpne</button></a>` : ""}
          </div></li>
        ${lendOpen ? `<form class="lendform" data-id="${it.id}"><input name="to" placeholder="Hvem låner?" required><input name="due" type="date" title="Tilbake innen (valgfritt)"><button class="small">Lån ut</button></form>` : ""}`;
    }

    _renderLent() {
      const el = this.shadowRoot?.getElementById("lent");
      if (!el || !this._hass) return;
      const st = this._state("lent");
      const items = st?.attributes?.items || [];
      if (!st) { el.innerHTML = `<div class="muted">Fant ikke Tingsted-sensorene.</div>`; return; }
      if (!items.length) { el.innerHTML = `<div class="muted">Ingenting er lånt ut.</div>`; return; }
      el.innerHTML = `<ul>${items.map((i) => this._itemRow({ id: i.id, name: i.name }, i.where, i.lent_to, i.due, null)).join("")}</ul>`;
    }

    _renderResults() {
      const el = this.shadowRoot?.getElementById("sres");
      if (!el) return;
      if (this._results === null) { el.innerHTML = ""; return; }
      const rows = this._results.map((r) => {
        const it = r.item || { id: null, name: r.type === "box" ? `Kasse ${r.box?.code}${r.box?.name ? " · " + r.box.name : ""}` : r.where, qty: null };
        return this._itemRow(it, r.where, it.lent_to, it.lent_due, r.box?.url);
      });
      el.innerHTML = (this._speech ? `<div class="speech">${esc(this._speech)}</div>` : "") +
        (rows.length ? `<ul>${rows.join("")}</ul>` : "");
    }

    async _search() {
      const q = this.shadowRoot.getElementById("q").value.trim();
      if (!q) { this._results = null; this._renderResults(); return; }
      const btn = this.shadowRoot.getElementById("sbtn");
      btn.disabled = true;
      try {
        const [where, res] = await Promise.all([this._call("find", { query: q }, true), this._call("search", { query: q }, true)]);
        this._speech = where?.speech || "";
        this._results = (res?.results || []).slice(0, 15);
      } catch (e) {
        this._speech = `Tingsted svarte ikke: ${e.message || e}`;
        this._results = [];
      }
      btn.disabled = false;
      this._renderResults();
    }

    async _click(e) {
      const b = e.target.closest("button[data-act]");
      if (!b) return;
      const id = Number(b.dataset.id);
      if (b.dataset.act === "lendopen") {
        this._lendOpen = this._lendOpen === id ? null : id;
        this._renderResults();
        this.shadowRoot.querySelector(`form.lendform[data-id="${id}"] input`)?.focus();
      } else if (b.dataset.act === "return") {
        this._busy.add(id); b.disabled = true;
        try { await this._call("return_item", { item_id: id }); this._toast("Levert tilbake."); }
        catch (err) { this._toast(`Feil: ${err.message || err}`); }
        this._busy.delete(id);
        if (this._results) this._search();
      }
    }

    async _lend(id, to, due) {
      if (!to.trim()) return;
      const data = { item_id: id, to: to.trim() };
      if (due) data.due = due;
      try { await this._call("lend", data); this._toast(`Lånt ut til ${to.trim()}.`); }
      catch (err) { this._toast(`Feil: ${err.message || err}`); }
      this._lendOpen = null;
      this._search();
    }

    async _add() {
      const box = this.shadowRoot.getElementById("abox").value.trim();
      const lines = this.shadowRoot.getElementById("aitems").value.split("\n").map((s) => s.trim()).filter(Boolean);
      const msg = this.shadowRoot.getElementById("amsg");
      if (!box || !lines.length) { msg.textContent = "Skriv kassekoden og minst én ting."; return; }
      try {
        const res = await this._call("add_items", { box, items: lines }, true);
        msg.textContent = `La til ${res?.added?.length ?? lines.length} ting i ${box}.`;
        this.shadowRoot.getElementById("aitems").value = "";
      } catch (err) { msg.textContent = `Feil: ${err.message || err}`; }
    }

    async _loadRecent() {
      const el = this.shadowRoot?.getElementById("recent");
      if (!el || this._loadingRecent) return;
      this._loadingRecent = true;
      try {
        const res = await this._call("recent", { limit: this._config.recent_limit || 8 }, true);
        const rows = res?.history || [];
        el.innerHTML = rows.length ? `<ul>${rows.map((h) => `<li class="row"><div class="grow"><div><b>${esc(h.who || "Noen")}</b> ${esc(h.text)}</div>
          <div class="sub">${ago(h.time)}</div></div></li>`).join("")}</ul>` : `<div class="muted">Ingen endringer ennå.</div>`;
      } catch (err) {
        el.innerHTML = `<div class="muted">Kunne ikke hente endringer: ${esc(err.message || err)}</div>`;
      }
      this._loadingRecent = false;
    }

    _toast(message) {
      this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
    }
  }

  if (!customElements.get("tingsted-card")) customElements.define("tingsted-card", TingstedCard);
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === "tingsted-card")) {
    window.customCards.push({ type: "tingsted-card", name: "Tingsted", preview: false,
      description: "Søk, lån ut, levert tilbake, legg i kasse og siste endringer i Tingsted." });
  }
})();

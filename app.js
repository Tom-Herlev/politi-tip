(() => {
  const TYPES = [
    { id: "brand", label: "Brand" },
    { id: "faerdsel", label: "Færdsel" },
    { id: "redning", label: "Redning" },
    { id: "politi", label: "Politi" },
    { id: "andet", label: "Andet" },
    { id: "tip", label: "Uofficielle tips" },
  ];
  const TYPE_LABEL = Object.fromEntries(TYPES.map((t) => [t.id, t.label]));
  const TYPE_COLOR = {
    brand: "#c45c26",
    faerdsel: "#c48a12",
    redning: "#1b7a72",
    politi: "#1c3a5f",
    andet: "#5d6570",
    tip: "#6b3fa0",
  };
  const STORAGE_DISTRICTS = "polititip.districts";
  const STORAGE_TYPES = "polititip.types";
  const STORAGE_TIPS = "polititip.tips";
  const AV_TOKEN = "adressevaelger123";
  const CPH = "Europe/Copenhagen";

  const state = {
    data: null,
    districts: [],
    types: new Set(TYPES.map((t) => t.id)),
    tips: [],
    markers: new Map(),
    activeId: null,
  };

  const els = {
    districtFilters: document.getElementById("district-filters"),
    typeFilters: document.getElementById("type-filters"),
    list: document.getElementById("list"),
    listCount: document.getElementById("list-count"),
    empty: document.getElementById("empty"),
    updated: document.getElementById("updated"),
    tipForm: document.getElementById("tip-form"),
    tipText: document.getElementById("tip-text"),
    tipAddress: document.getElementById("tip-address"),
    tipDistrict: document.getElementById("tip-district"),
    tipType: document.getElementById("tip-type"),
    tipStatus: document.getElementById("tip-status"),
    toggleFilters: document.getElementById("toggle-filters"),
    sidebar: document.getElementById("sidebar"),
  };

  const map = L.map("map", { zoomControl: true, scrollWheelZoom: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap-bidragydere",
  }).addTo(map);
  map.setView([55.68, 12.55], 10);
  const layer = L.layerGroup().addTo(map);

  function defaultDistricts(districts) {
    return districts.filter((d) => d.default_on).map((d) => d.id);
  }

  function loadDistricts(districts) {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_DISTRICTS) || "null");
      if (Array.isArray(raw) && raw.length) {
        const known = new Set(districts.map((d) => d.id));
        const kept = raw.filter((id) => known.has(id));
        if (kept.length) return kept;
      }
    } catch (_) { /* ignore */ }
    return defaultDistricts(districts);
  }

  function loadTypes() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_TYPES) || "null");
      if (Array.isArray(raw) && raw.length) return new Set(raw);
    } catch (_) { /* ignore */ }
    return new Set(TYPES.map((t) => t.id));
  }

  function loadTips() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_TIPS) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (_) {
      return [];
    }
  }

  function savePrefs() {
    localStorage.setItem(STORAGE_DISTRICTS, JSON.stringify(state.districts));
    localStorage.setItem(STORAGE_TYPES, JSON.stringify([...state.types]));
    localStorage.setItem(STORAGE_TIPS, JSON.stringify(state.tips));
  }

  function formatTime(iso) {
    if (!iso) return "";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return iso;
    const fmt = new Intl.DateTimeFormat("da-DK", {
      timeZone: CPH,
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
    return fmt.format(dt).replace(",", "") + " (dansk tid)";
  }

  function formatUpdated(iso) {
    if (!iso) return "Ukendt opdateringstidspunkt";
    const dt = new Date(iso);
    const fmt = new Intl.DateTimeFormat("da-DK", {
      timeZone: CPH,
      dateStyle: "long",
      timeStyle: "short",
    });
    return "Opdateret " + fmt.format(dt) + " (dansk tid)";
  }

  function markerIcon(type) {
    const color = TYPE_COLOR[type] || TYPE_COLOR.andet;
    const isTip = type === "tip";
    const html = `<div style="
      width:18px;height:18px;border-radius:50% 50% 50% 0;
      transform:rotate(-45deg);
      background:${color};
      border:2px solid #fff;
      box-shadow:0 1px 6px rgba(0,0,0,.35);
      ${isTip ? "outline:2px dashed #fff;outline-offset:1px;" : ""}
    "></div>`;
    return L.divIcon({
      className: "pin",
      html,
      iconSize: [18, 18],
      iconAnchor: [9, 18],
      popupAnchor: [0, -16],
    });
  }

  function allItems() {
    const official = (state.data && state.data.incidents) || [];
    return official.concat(state.tips);
  }

  function visibleItems() {
    const districts = new Set(state.districts);
    return allItems()
      .filter((item) => districts.has(item.district))
      .filter((item) => {
        const typ = item.official === false || item.source === "tip" ? "tip" : item.type;
        return state.types.has(typ);
      })
      .sort((a, b) => (b.updated_at || b.published_at || "").localeCompare(a.updated_at || a.published_at || ""));
  }

  function popupHtml(item) {
    const typ = item.source === "tip" ? "tip" : item.type;
    const src = item.source === "tip" ? "Uofficielt tip" : (item.source_label || "POLITI UPDATE");
    const loc = item.location_text ? `<p>${escapeHtml(item.location_text)}</p>` : "";
    const text = item.text ? `<p>${escapeHtml(item.text.slice(0, 280))}${item.text.length > 280 ? "…" : ""}</p>` : "";
    const link = item.url
      ? `<p><a href="${escapeAttr(item.url)}" target="_blank" rel="noopener">Åbn kilden</a></p>`
      : "";
    const del = item.source === "tip"
      ? `<p><button type="button" data-del="${escapeAttr(item.id)}">Fjern mit tip</button></p>`
      : "";
    return `<div class="popup">
      <h3>${escapeHtml(item.title)}</h3>
      <p><strong>${escapeHtml(TYPE_LABEL[typ] || typ)}</strong> · ${escapeHtml(src)}</p>
      <p>${escapeHtml(formatTime(item.updated_at || item.published_at))}</p>
      ${loc}${text}${link}${del}
    </div>`;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function renderFilters() {
    const districts = state.data.districts;
    els.districtFilters.innerHTML = districts.map((d) => `
      <label>
        <input type="checkbox" data-district="${d.id}" ${state.districts.includes(d.id) ? "checked" : ""} />
        <span>${escapeHtml(d.name)} <small>${escapeHtml(d.short)} · ${d.count} meddelelser</small></span>
      </label>
    `).join("");
    els.typeFilters.innerHTML = TYPES.map((t) => `
      <label>
        <input type="checkbox" data-type="${t.id}" ${state.types.has(t.id) ? "checked" : ""} />
        <span>${escapeHtml(t.label)}</span>
      </label>
    `).join("");
    els.tipDistrict.innerHTML = districts.map((d) =>
      `<option value="${d.id}">${escapeHtml(d.name)}</option>`
    ).join("");
    const preferred = ["koebenhavn", "vestegnen", "nordsjaelland"].find((id) => state.districts.includes(id))
      || state.districts[0]
      || districts[0].id;
    els.tipDistrict.value = preferred;
  }

  function render(opts) {
    const fitMap = !opts || opts.fitMap !== false;
    const items = visibleItems();
    els.listCount.textContent = items.length === 1 ? "1 hændelse" : `${items.length} hændelser`;
    els.empty.hidden = items.length !== 0;
    els.list.innerHTML = items.map((item) => {
      const typ = item.source === "tip" ? "tip" : item.type;
      const loc = item.location_text || (item.lat == null ? "Intet sted angivet" : "");
      const src = item.source === "tip" ? "Uofficielt tip" : item.district_name;
      return `<li class="item ${typ}${state.activeId === item.id ? " active" : ""}" data-id="${escapeAttr(item.id)}">
        <span class="bar"></span>
        <div>
          <h3>${escapeHtml(item.title)}</h3>
          <p>
            <span class="badge${typ === "tip" ? " tip" : ""}">${escapeHtml(TYPE_LABEL[typ] || typ)}</span>
            ${escapeHtml(loc)}${loc ? " · " : ""}${escapeHtml(src)}
          </p>
        </div>
        <div class="meta">${escapeHtml(formatTime(item.updated_at || item.published_at))}</div>
      </li>`;
    }).join("");

    layer.clearLayers();
    state.markers.clear();
    const bounds = [];
    for (const item of items) {
      if (item.lat == null || item.lon == null) continue;
      const typ = item.source === "tip" ? "tip" : item.type;
      const marker = L.marker([item.lat, item.lon], { icon: markerIcon(typ), title: item.title });
      marker.bindPopup(popupHtml(item));
      marker.on("click", () => selectItem(item.id, false));
      marker.addTo(layer);
      state.markers.set(item.id, marker);
      bounds.push([item.lat, item.lon]);
    }
    if (fitMap) {
      if (bounds.length === 1) {
        map.setView(bounds[0], 13);
      } else if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [28, 28], maxZoom: 13 });
      } else if (state.districts.length <= 3 && state.districts.every((id) => ["koebenhavn", "vestegnen", "nordsjaelland"].includes(id))) {
        map.setView([55.76, 12.4], 10);
      } else {
        map.setView([56.0, 10.5], 7);
      }
    }
  }

  function selectItem(id, pan) {
    state.activeId = id;
    for (const li of els.list.querySelectorAll(".item")) {
      li.classList.toggle("active", li.dataset.id === id);
    }
    const marker = state.markers.get(id);
    if (marker) {
      if (pan !== false) {
        map.setView(marker.getLatLng(), Math.max(map.getZoom(), 12));
      }
      marker.openPopup();
    }
    const li = els.list.querySelector(`.item[data-id="${CSS.escape(id)}"]`);
    if (li && pan !== false) li.scrollIntoView({ block: "nearest" });
  }

  function bindUi() {
    els.districtFilters.addEventListener("change", (e) => {
      const input = e.target.closest("input[data-district]");
      if (!input) return;
      const id = input.dataset.district;
      if (input.checked && !state.districts.includes(id)) state.districts.push(id);
      if (!input.checked) state.districts = state.districts.filter((x) => x !== id);
      if (!state.districts.length) {
        input.checked = true;
        state.districts = [id];
      }
      savePrefs();
      render();
    });
    els.typeFilters.addEventListener("change", (e) => {
      const input = e.target.closest("input[data-type]");
      if (!input) return;
      if (input.checked) state.types.add(input.dataset.type);
      else state.types.delete(input.dataset.type);
      savePrefs();
      render();
    });
    document.getElementById("select-mine").addEventListener("click", () => {
      state.districts = defaultDistricts(state.data.districts);
      savePrefs();
      renderFilters();
      render();
    });
    document.getElementById("select-all").addEventListener("click", () => {
      state.districts = state.data.districts.map((d) => d.id);
      savePrefs();
      renderFilters();
      render();
    });
    els.list.addEventListener("click", (e) => {
      const li = e.target.closest(".item");
      if (li) selectItem(li.dataset.id, true);
    });
    map.on("popupopen", (ev) => {
      const btn = ev.popup.getElement()?.querySelector("[data-del]");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-del");
        state.tips = state.tips.filter((t) => t.id !== id);
        savePrefs();
        render();
      });
    });
    els.toggleFilters.addEventListener("click", () => {
      const open = els.sidebar.classList.toggle("open");
      els.toggleFilters.setAttribute("aria-expanded", String(open));
    });
    els.tipForm.addEventListener("submit", onAddTip);
  }

  async function onAddTip(ev) {
    ev.preventDefault();
    const text = els.tipText.value.trim();
    const address = els.tipAddress.value.trim();
    const district = els.tipDistrict.value;
    const typ = els.tipType.value;
    if (!text) return;
    showTipStatus("Geokoder stedet …", false);
    const query = address || text;
    const geo = await geocodeClient(query, district);
    const urlMatch = text.match(/https?:\/\/\S+/i);
    const title = text.replace(/https?:\/\/\S+/gi, "").trim() || "Uofficielt tip";
    const districtName = (state.data.districts.find((d) => d.id === district) || {}).name || district;
    const now = new Date().toISOString();
    const tip = {
      id: "tip-" + Date.now(),
      source: "tip",
      source_label: "Uofficielt tip",
      official: false,
      district,
      district_name: districtName,
      type: typ,
      title: title.slice(0, 140),
      text,
      location_text: address || (geo && geo.label) || null,
      lat: geo ? geo.lat : null,
      lon: geo ? geo.lon : null,
      geocode_source: geo ? geo.source : null,
      published_at: now,
      updated_at: now,
      url: urlMatch ? urlMatch[0] : null,
      update_count: 1,
    };
    state.tips.unshift(tip);
    if (!state.districts.includes(district)) state.districts.push(district);
    if (!state.types.has("tip")) state.types.add("tip");
    savePrefs();
    renderFilters();
    render();
    els.tipForm.reset();
    els.tipDistrict.value = district;
    showTipStatus(geo
      ? "Tip tilføjet og sat på kortet."
      : "Tip tilføjet til listen. Stedet kunne ikke geokodes, så der er ingen nål.", false);
    if (geo) selectItem(tip.id, true);
  }

  function showTipStatus(msg, isError) {
    els.tipStatus.hidden = false;
    els.tipStatus.textContent = msg;
    els.tipStatus.classList.toggle("error", !!isError);
  }

  function utm32nToWgs84(easting, northing) {
    const a = 6378137.0;
    const f = 1 / 298.257222101;
    const k0 = 0.9996;
    const e2 = f * (2 - f);
    const ep2 = e2 / (1 - e2);
    const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
    const x = easting - 500000.0;
    const y = northing;
    const m = y / k0;
    const mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256));
    const phi1 = mu
      + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu)
      + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
      + (151 * e1 ** 3 / 96) * Math.sin(6 * mu)
      + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
    const sinp = Math.sin(phi1);
    const cosp = Math.cos(phi1);
    const n1 = a / Math.sqrt(1 - e2 * sinp ** 2);
    const t1 = Math.tan(phi1) ** 2;
    const c1 = ep2 * cosp ** 2;
    const r1 = a * (1 - e2) / Math.pow(1 - e2 * sinp ** 2, 1.5);
    const d = x / (n1 * k0);
    const lat = phi1 - (n1 * Math.tan(phi1) / r1) * (
      d ** 2 / 2
      - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
      + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720
    );
    const lon = (9 * Math.PI / 180) + (
      d
      - (1 + 2 * t1 + c1) * d ** 3 / 6
      + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120
    ) / cosp;
    return { lat: lat * 180 / Math.PI, lon: lon * 180 / Math.PI };
  }

  async function geocodeClient(query, district) {
    try {
      const av = await fetch("https://adressevaelger.dk/husnumre/soeg?" + new URLSearchParams({
        tekst: query,
        token: AV_TOKEN,
      }));
      if (av.ok) {
        const data = await av.json();
        const hits = data.fund || [];
        let hid = null;
        let label = null;
        const hus = hits.find((h) => (h.type || "").toLowerCase() === "husnummer");
        if (hus) {
          hid = hus.id;
          label = hus.titel;
        } else if (hits[0] && hits[0].vejnavn) {
          const again = await fetch("https://adressevaelger.dk/husnumre/soeg?" + new URLSearchParams({
            tekst: `${hits[0].vejnavn} ${hits[0].postnr || ""}`.trim(),
            token: AV_TOKEN,
          }));
          if (again.ok) {
            const more = await again.json();
            const h2 = (more.fund || []).find((h) => (h.type || "").toLowerCase() === "husnummer");
            if (h2) {
              hid = h2.id;
              label = h2.titel;
            }
          }
        }
        if (hid) {
          const look = await fetch(`https://adressevaelger.dk/husnumre/${hid}?token=${AV_TOKEN}`);
          if (look.ok) {
            const det = await look.json();
            const xy = det.husnummer && det.husnummer.adgangspunkt && det.husnummer.adgangspunkt.koordinater;
            if (xy && xy.x != null) {
              const { lat, lon } = utm32nToWgs84(xy.x, xy.y);
              return {
                lat, lon,
                label: (det.husnummer && det.husnummer.adgangsadressebetegnelse) || label || query,
                source: "adressevaelger",
              };
            }
          }
        }
      }
    } catch (_) { /* fallback */ }
    try {
      const url = "https://nominatim.openstreetmap.org/search?" + new URLSearchParams({
        q: query + ", Danmark",
        format: "json",
        limit: "1",
        countrycodes: "dk",
      });
      const res = await fetch(url, { headers: { "Accept": "application/json" } });
      if (res.ok) {
        const data = await res.json();
        if (data[0]) {
          return {
            lat: parseFloat(data[0].lat),
            lon: parseFloat(data[0].lon),
            label: data[0].display_name,
            source: "nominatim",
          };
        }
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  const REFRESH_MS = 2 * 60 * 1000;
  let lastFetchedAt = null;
  let refreshTimer = null;
  let refreshing = false;

  function formatClock(date) {
    return new Intl.DateTimeFormat("da-DK", {
      timeZone: CPH,
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function showUpdated() {
    if (!state.data) return;
    const source = formatUpdated(state.data.generated_at);
    if (!lastFetchedAt) {
      els.updated.textContent = source;
      return;
    }
    els.updated.textContent = source + " · tjekket kl. " + formatClock(lastFetchedAt);
  }

  async function loadData(opts) {
    const silent = opts && opts.silent;
    const fitMap = !opts || opts.fitMap !== false;
    if (refreshing) return;
    refreshing = true;
    try {
      const res = await fetch("data.json", { cache: "no-store" });
      if (!res.ok) throw new Error("Kunne ikke hente data.json");
      const data = await res.json();
      const prev = state.data && state.data.generated_at;
      const changed = prev !== data.generated_at;
      state.data = data;
      lastFetchedAt = new Date();
      if (!state.districts.length) {
        state.districts = loadDistricts(state.data.districts);
      }
      showUpdated();
      if (changed || !silent) {
        renderFilters();
        render({ fitMap: fitMap && !silent });
      }
    } catch (err) {
      if (!state.data) {
        els.updated.textContent = "Kunne ikke indlæse data.json. Åbn siden via en webadresse, ikke som fil.";
      } else if (!silent) {
        showUpdated();
      }
    } finally {
      refreshing = false;
    }
  }

  function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => loadData({ silent: true, fitMap: false }), REFRESH_MS);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        loadData({ silent: true, fitMap: false });
      }
    });
    window.addEventListener("focus", () => loadData({ silent: true, fitMap: false }));
  }

  async function init() {
    state.types = loadTypes();
    state.tips = loadTips();
    bindUi();
    await loadData({ silent: false, fitMap: true });
    startAutoRefresh();
  }

  init();
})();

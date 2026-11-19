(() => {
  const CATEGORIES = [
    { id: "politi", label: "Politi" },
    { id: "brand", label: "Brand/redning" },
    { id: "trafik", label: "Trafik" },
    { id: "strom", label: "Strøm" },
    { id: "vejr", label: "Vejr" },
    { id: "helikopter", label: "Helikopter" },
    { id: "tip", label: "Tips" },
  ];
  const CAT_LABEL = Object.fromEntries(CATEGORIES.map((t) => [t.id, t.label]));
  const CAT_COLOR = {
    politi: "#1c3a5f",
    brand: "#c45c26",
    trafik: "#c48a12",
    strom: "#c9a227",
    vejr: "#3d6ea8",
    helikopter: "#8b1e3f",
    tip: "#6b3fa0",
  };
  const TYPE_LABEL = {
    brand: "Brand",
    faerdsel: "Færdsel",
    redning: "Redning",
    politi: "Politi",
    andet: "Andet",
    tip: "Uofficielt tip",
  };
  const TIME_OPTIONS = [
    { hours: 1, label: "1 t" },
    { hours: 6, label: "6 t" },
    { hours: 24, label: "24 t" },
    { hours: 48, label: "48 t" },
  ];
  const STORAGE_DISTRICTS = "polititip.districts";
  const STORAGE_CATEGORIES = "polititip.categories";
  const STORAGE_TIPS = "polititip.tips";
  const STORAGE_TIME = "polititip.timeHours";
  const STORAGE_ROUTINE = "polititip.showRoutine";
  const STORAGE_RADIUS = "polititip.nearRadius";
  const AV_TOKEN = "adressevaelger123";
  const CPH = "Europe/Copenhagen";
  const ADSB_REG_URL = "https://api.adsb.lol/v2/reg/";
  const ADSB_POINT_URL = "https://api.adsb.lol/v2/lat/56.0/lon/10.0/dist/250";
  const HEMS_POLL_MS = 20000;
  const BBOX = {
    koebenhavn: [55.58, 12.40, 55.78, 12.72],
    vestegnen: [55.58, 12.10, 55.78, 12.52],
    nordsjaelland: [55.70, 11.80, 56.16, 12.65],
    midtvestsjaelland: [55.15, 10.85, 55.98, 12.40],
    sydsjaelland: [54.50, 10.85, 55.45, 12.55],
    fyn: [54.70, 9.60, 55.65, 10.95],
    sydsonderjylland: [54.73, 8.05, 55.80, 9.95],
    sydostjylland: [55.30, 9.10, 56.00, 10.20],
    midtvestjylland: [55.65, 8.05, 57.20, 9.85],
    ostjylland: [55.80, 9.65, 56.65, 10.90],
    nordjylland: [56.50, 8.05, 57.80, 11.35],
    bornholm: [54.94, 14.63, 55.32, 15.26],
  };

  const state = {
    data: null,
    districts: [],
    categories: new Set(CATEGORIES.map((t) => t.id)),
    tips: [],
    markers: new Map(),
    activeId: null,
    timeHours: 24,
    showRoutine: false,
    near: null, // {lat, lon}
    nearRadiusKm: 25,
    hemsLive: null,
    hemsCors: null,
  };

  const els = {
    districtFilters: document.getElementById("district-filters"),
    categoryFilters: document.getElementById("category-filters"),
    timeFilters: document.getElementById("time-filters"),
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
    mapToolbar: document.getElementById("map-toolbar"),
    showRoutine: document.getElementById("show-routine"),
    nearMe: document.getElementById("near-me"),
    nearControls: document.getElementById("near-controls"),
    nearRadius: document.getElementById("near-radius"),
    nearOff: document.getElementById("near-off"),
    nearStatus: document.getElementById("near-status"),
  };

  const map = L.map("map", { zoomControl: true, scrollWheelZoom: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap-bidragydere",
  }).addTo(map);
  map.setView([55.68, 12.55], 10);
  const layer = L.layerGroup().addTo(map);

  function categoryOf(item) {
    if (item.official === false || item.source === "tip") return "tip";
    return item.category || "politi";
  }

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

  function loadCategories() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_CATEGORIES) || "null");
      if (Array.isArray(raw) && raw.length) return new Set(raw);
    } catch (_) { /* ignore */ }
    return new Set(CATEGORIES.map((t) => t.id));
  }

  function loadTips() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_TIPS) || "[]");
      return Array.isArray(raw) ? raw : [];
    } catch (_) {
      return [];
    }
  }

  function loadTimeHours() {
    const n = parseInt(localStorage.getItem(STORAGE_TIME) || "24", 10);
    return TIME_OPTIONS.some((o) => o.hours === n) ? n : 24;
  }

  function savePrefs() {
    localStorage.setItem(STORAGE_DISTRICTS, JSON.stringify(state.districts));
    localStorage.setItem(STORAGE_CATEGORIES, JSON.stringify([...state.categories]));
    localStorage.setItem(STORAGE_TIPS, JSON.stringify(state.tips));
    localStorage.setItem(STORAGE_TIME, String(state.timeHours));
    localStorage.setItem(STORAGE_ROUTINE, state.showRoutine ? "1" : "0");
    localStorage.setItem(STORAGE_RADIUS, String(state.nearRadiusKm));
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

  function inDistrict(lat, lon, districtId) {
    const box = BBOX[districtId];
    if (!box || lat == null || lon == null) return false;
    const [south, west, north, east] = box;
    const pad = 0.08;
    return lat >= south - pad && lat <= north + pad && lon >= west - pad && lon <= east + pad;
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const toR = (d) => (d * Math.PI) / 180;
    const dLat = toR(lat2 - lat1);
    const dLon = toR(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2
      + Math.cos(toR(lat1)) * Math.cos(toR(lat2)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  function formatDistance(km) {
    if (km == null || Number.isNaN(km)) return "";
    if (km < 1) return Math.round(km * 1000) + " m";
    return km.toLocaleString("da-DK", { maximumFractionDigits: 1 }) + " km";
  }

  function markerIcon(cat, extra) {
    const color = CAT_COLOR[cat] || CAT_COLOR.politi;
    const isTip = cat === "tip";
    const hems = cat === "helikopter";
    const rot = extra && extra.track != null ? Number(extra.track) : 0;
    const html = hems
      ? `<div style="width:22px;height:22px;transform:rotate(${rot}deg);display:flex;align-items:center;justify-content:center;filter:drop-shadow(0 1px 3px rgba(0,0,0,.4));">
           <svg viewBox="0 0 24 24" width="22" height="22"><path fill="${color}" stroke="#fff" stroke-width="1.4" d="M12 2 L15 14 L12 12 L9 14 Z"/></svg>
         </div>`
      : `<div style="
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
      iconSize: [22, 22],
      iconAnchor: hems ? [11, 11] : [9, 18],
      popupAnchor: [0, hems ? -12 : -16],
    });
  }

  function allItems() {
    const official = (state.data && state.data.incidents) || [];
    const live = state.hemsLive;
    let list = official;
    if (live && live.length) {
      const byReg = new Map(live.map((h) => [h.registration, h]));
      list = official.filter((i) => categoryOf(i) !== "helikopter" || !byReg.has(i.registration));
      list = list.concat(live);
    }
    return list.concat(state.tips);
  }

  function itemAgeMs(item) {
    const iso = item.updated_at || item.published_at;
    if (!iso) return Infinity;
    const t = new Date(iso).getTime();
    return Number.isNaN(t) ? Infinity : Date.now() - t;
  }

  function visibleItems() {
    const districts = new Set(state.districts);
    const cutoff = state.timeHours * 3600 * 1000;
    return allItems()
      .filter((item) => {
        if (item.routine && !state.showRoutine) return false;
        const cat = categoryOf(item);
        if (!state.categories.has(cat)) return false;
        if (item.nationwide || cat === "vejr" && item.district == null) {
          // vis landsdækkende varsler, når en kategori er slået til
        } else if (item.district && districts.has(item.district)) {
          // ok
        } else if (item.lat != null && item.lon != null) {
          const hit = [...districts].some((id) => inDistrict(item.lat, item.lon, id));
          if (!hit) return false;
        } else if (item.district && !districts.has(item.district)) {
          return false;
        }
        if (!item.ongoing && cat !== "helikopter") {
          if (itemAgeMs(item) > cutoff) return false;
        }
        if (state.near && item.lat != null && item.lon != null) {
          const km = haversineKm(state.near.lat, state.near.lon, item.lat, item.lon);
          item._distanceKm = km;
          if (km > state.nearRadiusKm) return false;
        } else if (state.near && (item.lat == null || item.lon == null)) {
          return false;
        } else if (state.near) {
          item._distanceKm = null;
        } else if (state.near === null) {
          item._distanceKm = null;
        }
        return true;
      })
      .map((item) => {
        if (state.near && item.lat != null && item.lon != null && item._distanceKm == null) {
          item._distanceKm = haversineKm(state.near.lat, state.near.lon, item.lat, item.lon);
        } else if (!state.near) {
          item._distanceKm = null;
        }
        return item;
      })
      .sort((a, b) => {
        if (state.near && a._distanceKm != null && b._distanceKm != null) {
          return a._distanceKm - b._distanceKm;
        }
        return (b.updated_at || b.published_at || "").localeCompare(a.updated_at || a.published_at || "");
      });
  }

  function categoryCounts() {
    const districts = new Set(state.districts);
    const cutoff = state.timeHours * 3600 * 1000;
    const counts = Object.fromEntries(CATEGORIES.map((c) => [c.id, 0]));
    for (const item of allItems()) {
      if (item.routine && !state.showRoutine) continue;
      const cat = categoryOf(item);
      if (!counts.hasOwnProperty(cat)) continue;
      const inArea = item.nationwide
        || (item.district && districts.has(item.district))
        || (item.lat != null && [...districts].some((id) => inDistrict(item.lat, item.lon, id)));
      if (!inArea && !(item.district == null && item.lat == null)) continue;
      if (!item.ongoing && cat !== "helikopter" && itemAgeMs(item) > cutoff) continue;
      if (state.near && item.lat != null) {
        const km = haversineKm(state.near.lat, state.near.lon, item.lat, item.lon);
        if (km > state.nearRadiusKm) continue;
      }
      counts[cat] += 1;
    }
    return counts;
  }

  function sourceLink(item) {
    const url = item.source_url || item.url;
    const label = item.attribution
      || (item.source === "odin"
        ? "Kilde: www.odin.dk/112puls"
        : (item.source_label ? "Kilde: " + item.source_label : "Kilde"));
    if (!url) return escapeHtml(label);
    return `<a class="source-link" href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
  }

  function extraLines(item) {
    const bits = [];
    if (item.reopening) bits.push("Forventes åbnet: " + item.reopening + (/\(dansk tid\)/.test(item.reopening) ? "" : " (dansk tid)"));
    if (item.customers != null) bits.push(item.customers + " kunder berørt" + (item.utility ? " · " + item.utility : ""));
    else if (item.utility) bits.push("Elselskab: " + item.utility);
    if (item.approximate && item.station) bits.push("Omtrentligt område omkring " + item.station + " (ODIN giver ikke en adresse).");
    if (item.airborne) {
      const track = item.track != null ? " · kurs " + Math.round(item.track) + "°" : "";
      const alt = item.altitude_ft && item.altitude_ft !== "ground" ? " · " + item.altitude_ft + " ft" : "";
      bits.push("I luften" + track + alt);
    }
    if (item.expected_back) bits.push("Forventet tilbage: " + item.expected_back);
    return bits;
  }

  function popupHtml(item) {
    const cat = categoryOf(item);
    const typ = item.source === "tip" ? "tip" : item.type;
    const loc = item.location_text ? `<p>${escapeHtml(item.location_text)}</p>` : "";
    const text = item.text ? `<p>${escapeHtml(item.text.slice(0, 360))}${item.text.length > 360 ? "…" : ""}</p>` : "";
    const extras = extraLines(item).map((x) => `<p>${escapeHtml(x)}</p>`).join("");
    const dist = item._distanceKm != null ? `<p>Afstand: ${escapeHtml(formatDistance(item._distanceKm))}</p>` : "";
    const del = item.source === "tip"
      ? `<p><button type="button" data-del="${escapeAttr(item.id)}">Fjern mit tip</button></p>`
      : "";
    return `<div class="popup">
      <h3>${escapeHtml(item.title)}</h3>
      <p><strong>${escapeHtml(CAT_LABEL[cat] || cat)}</strong>${typ && TYPE_LABEL[typ] ? " · " + escapeHtml(TYPE_LABEL[typ]) : ""}</p>
      <p>${escapeHtml(formatTime(item.updated_at || item.published_at))}</p>
      ${loc}${text}${extras}${dist}
      <p>${sourceLink(item)}</p>
      ${del}
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
        <span>${escapeHtml(d.name)} <small>${escapeHtml(d.short)} · ${d.count} i kilden</small></span>
      </label>
    `).join("");
    const counts = categoryCounts();
    els.categoryFilters.innerHTML = CATEGORIES.map((t) => `
      <label class="count-chip">
        <input type="checkbox" data-category="${t.id}" ${state.categories.has(t.id) ? "checked" : ""} />
        <span>${escapeHtml(t.label)} <small>${counts[t.id] || 0}</small></span>
      </label>
    `).join("");
    els.timeFilters.innerHTML = TIME_OPTIONS.map((o) => `
      <label>
        <input type="radio" name="time-filter" data-hours="${o.hours}" ${state.timeHours === o.hours ? "checked" : ""} />
        <span>${escapeHtml(o.label)}</span>
      </label>
    `).join("");
    if (els.mapToolbar) {
      els.mapToolbar.innerHTML = CATEGORIES.filter((t) => t.id !== "tip" || counts[t.id]).map((t) => `
        <span class="tag" style="color:${CAT_COLOR[t.id]}">
          <span class="dot"></span>${escapeHtml(t.label)} ${counts[t.id] || 0}
        </span>
      `).join("");
    }
    els.showRoutine.checked = state.showRoutine;
    els.nearRadius.value = String(state.nearRadiusKm);
    els.nearControls.hidden = !state.near;
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
      const cat = categoryOf(item);
      const typ = item.source === "tip" ? "tip" : item.type;
      const loc = item.location_text || (item.lat == null ? "Intet sted angivet" : "");
      const dist = item._distanceKm != null ? `<span class="dist">${escapeHtml(formatDistance(item._distanceKm))}</span>` : "";
      const extra = extraLines(item)[0] ? " · " + extraLines(item)[0] : "";
      return `<li class="item category-${cat} ${typ}${state.activeId === item.id ? " active" : ""}" data-id="${escapeAttr(item.id)}">
        <span class="bar"></span>
        <div>
          <h3>${escapeHtml(item.title)}</h3>
          <p>
            <span class="badge ${cat}${typ === "tip" ? " tip" : ""}">${escapeHtml(CAT_LABEL[cat] || cat)}</span>
            ${escapeHtml(loc)}${loc ? " · " : ""}${sourceLink(item)}${escapeHtml(extra)}
            ${dist}
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
      const cat = categoryOf(item);
      const color = CAT_COLOR[cat] || CAT_COLOR.politi;
      let marker;
      if (item.geometry === "circle" || item.approximate || item.radius_m) {
        const radius = Math.max(120, Number(item.radius_m) || 2000);
        const circle = L.circle([item.lat, item.lon], {
          radius,
          color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.18,
          className: "leaflet-approx-circle",
        });
        circle.bindPopup(popupHtml(item));
        circle.on("click", () => selectItem(item.id, false));
        circle.addTo(layer);
        marker = circle;
        const southWest = L.latLng(item.lat, item.lon);
        bounds.push(southWest);
      } else {
        marker = L.marker([item.lat, item.lon], { icon: markerIcon(cat, item), title: item.title });
        marker.bindPopup(popupHtml(item));
        marker.on("click", () => selectItem(item.id, false));
        marker.addTo(layer);
        bounds.push([item.lat, item.lon]);
      }
      state.markers.set(item.id, marker);
    }
    if (state.near) {
      const here = L.circleMarker([state.near.lat, state.near.lon], {
        radius: 7, color: "#1c3a5f", fillColor: "#5aa0e6", fillOpacity: 1, weight: 2,
      }).bindPopup("Din position (kun på denne enhed)");
      here.addTo(layer);
    }
    const applyView = () => {
      map.invalidateSize();
      if (!fitMap) return;
      if (bounds.length === 1) {
        map.setView(bounds[0], 12);
      } else if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
      } else if (state.districts.length <= 3 && state.districts.every((id) => ["koebenhavn", "vestegnen", "nordsjaelland"].includes(id))) {
        map.setView([55.76, 12.4], 10);
      } else {
        map.setView([56.0, 10.5], 7);
      }
    };
    applyView();
    requestAnimationFrame(() => applyView());
    setTimeout(applyView, 250);
  }

  function selectItem(id, pan) {
    state.activeId = id;
    for (const li of els.list.querySelectorAll(".item")) {
      li.classList.toggle("active", li.dataset.id === id);
    }
    const marker = state.markers.get(id);
    if (marker) {
      if (pan !== false) {
        const ll = marker.getLatLng ? marker.getLatLng() : marker.getBounds().getCenter();
        map.setView(ll, Math.max(map.getZoom(), 11));
      }
      if (marker.openPopup) marker.openPopup();
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
      renderFilters();
      render();
    });
    els.categoryFilters.addEventListener("change", (e) => {
      const input = e.target.closest("input[data-category]");
      if (!input) return;
      if (input.checked) state.categories.add(input.dataset.category);
      else state.categories.delete(input.dataset.category);
      savePrefs();
      renderFilters();
      render();
    });
    els.timeFilters.addEventListener("change", (e) => {
      const input = e.target.closest("input[data-hours]");
      if (!input) return;
      state.timeHours = parseInt(input.dataset.hours, 10);
      savePrefs();
      renderFilters();
      render();
    });
    els.showRoutine.addEventListener("change", () => {
      state.showRoutine = els.showRoutine.checked;
      savePrefs();
      renderFilters();
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
      if (e.target.closest("a")) return;
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
    els.nearMe.addEventListener("click", enableNearMe);
    els.nearOff.addEventListener("click", () => {
      state.near = null;
      els.nearControls.hidden = true;
      els.nearStatus.hidden = true;
      renderFilters();
      render();
    });
    els.nearRadius.addEventListener("change", () => {
      state.nearRadiusKm = parseInt(els.nearRadius.value, 10) || 25;
      savePrefs();
      renderFilters();
      render();
    });
  }

  function enableNearMe() {
    if (!navigator.geolocation) {
      els.nearStatus.hidden = false;
      els.nearStatus.classList.add("error");
      els.nearStatus.textContent = "Denne enhed understøtter ikke stedbestemmelse.";
      return;
    }
    els.nearStatus.hidden = false;
    els.nearStatus.classList.remove("error");
    els.nearStatus.textContent = "Henter din position …";
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        state.near = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        els.nearControls.hidden = false;
        els.nearStatus.textContent = "Viser hændelser inden for " + state.nearRadiusKm + " km.";
        renderFilters();
        render({ fitMap: true });
      },
      () => {
        els.nearStatus.classList.add("error");
        els.nearStatus.textContent = "Kunne ikke hente positionen. Tillad stedbestemmelse i browseren, hvis du vil bruge Nær mig.";
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 }
    );
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
      source_url: urlMatch ? urlMatch[0] : null,
      official: false,
      category: "tip",
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
    if (!state.categories.has("tip")) state.categories.add("tip");
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
    const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2));
    const x = easting - 500000;
    const y = northing;
    const m = y / k0;
    const mu = m / (a * (1 - e2 / 4 - (3 * e2 ** 2) / 64 - (5 * e2 ** 3) / 256));
    const phi1 = mu
      + ((3 * e1) / 2 - (27 * e1 ** 3) / 32) * Math.sin(2 * mu)
      + ((21 * e1 ** 2) / 16 - (55 * e1 ** 4) / 32) * Math.sin(4 * mu)
      + ((151 * e1 ** 3) / 96) * Math.sin(6 * mu);
    const n1 = a / Math.sqrt(1 - e2 * Math.sin(phi1) ** 2);
    const t1 = Math.tan(phi1) ** 2;
    const c1 = (e2 / (1 - e2)) * Math.cos(phi1) ** 2;
    const r1 = (a * (1 - e2)) / Math.pow(1 - e2 * Math.sin(phi1) ** 2, 1.5);
    const d = x / (n1 * k0);
    const lat = phi1 - (n1 * Math.tan(phi1) / r1) * (
      (d ** 2) / 2
      - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * (e2 / (1 - e2))) * (d ** 4) / 24
      + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * (e2 / (1 - e2)) - 3 * c1 ** 2) * (d ** 6) / 720
    );
    const lon0 = 9 * Math.PI / 180;
    const lon = lon0 + (
      d
      - (1 + 2 * t1 + c1) * (d ** 3) / 6
      + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * (e2 / (1 - e2)) + 24 * t1 ** 2) * (d ** 5) / 120
    ) / Math.cos(phi1);
    return { lat: lat * 180 / Math.PI, lon: lon * 180 / Math.PI };
  }

  async function geocodeClient(query, district) {
    try {
      const url = "https://adressevaelger.dk/husnumre/soeg?" + new URLSearchParams({
        tekst: query,
        token: AV_TOKEN,
      });
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const hits = data.fund || [];
        const hus = hits.find((h) => (h.type || "").toLowerCase() === "husnummer") || hits[0];
        if (hus && hus.id) {
          const det = await fetch(`https://adressevaelger.dk/husnumre/${hus.id}?token=${AV_TOKEN}`);
          if (det.ok) {
            const body = await det.json();
            const hn = body.husnummer || body;
            const coords = ((hn.adgangspunkt || {}).koordinater) || {};
            if (coords.x && coords.y) {
              const wgs = utm32nToWgs84(Number(coords.x), Number(coords.y));
              return {
                lat: wgs.lat,
                lon: wgs.lon,
                label: hn.adgangsadressebetegnelse || hus.titel || query,
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
  let hemsTimer = null;
  let hemsFailCount = 0;

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
    const bits = [source];
    if (lastFetchedAt) bits.push("tjekket kl. " + formatClock(lastFetchedAt));
    if (state.hemsCors === false) bits.push("helikopterposition fra datafeedet");
    else if (state.hemsCors === true) bits.push("live helikopter");
    els.updated.textContent = bits.join(" · ");
  }

  function hemsToIncident(ac, nowIso) {
    const reg = (ac.r || ac.registration || "").trim();
    const flight = (ac.flight || ac.callsign || "").trim();
    const typ = ac.t || ac.type || ac.aircraft_type || "";
    const alt = ac.alt_baro || ac.alt_geom || ac.altitude_ft;
    const airborne = alt !== "ground" && alt !== 0 && alt != null;
    const track = ac.track || ac.true_heading || ac.mag_heading;
    const title = "Akutlægehelikopter " + (reg || "") + (flight ? " (" + flight + ")" : "");
    return {
      id: "hems-" + (reg || ac.hex || Math.random()),
      category: "helikopter",
      type: "redning",
      title,
      text: airborne ? "I luften." : "Seneste position.",
      source: "adsb",
      source_label: "adsb.lol",
      source_url: "https://adsb.lol/",
      url: "https://adsb.lol/",
      published_at: nowIso,
      updated_at: nowIso,
      lat: Number(ac.lat),
      lon: Number(ac.lon),
      location_text: "Live position",
      official: true,
      ongoing: true,
      registration: reg,
      callsign: flight || null,
      aircraft_type: typ,
      track,
      altitude_ft: alt,
      speed_kt: ac.gs || ac.speed_kt,
      airborne: !!airborne,
      nationwide: false,
    };
  }

  function isHemsAc(ac) {
    const reg = (ac.r || "").replace(/\s+/g, "").toUpperCase();
    const typ = (ac.t || "").toUpperCase();
    const flight = (ac.flight || "").trim().toUpperCase();
    const types = { EC35: 1, EC45: 1, H135: 1, H145: 1, E135: 1, E145: 1 };
    return typ in types && (reg.startsWith("LN-OU") || reg.startsWith("LN-OT") || flight.startsWith("DOC") || flight.startsWith("NLA"));
  }

  async function pollHems() {
    if (state.hemsCors === false) return;
    try {
      const res = await fetch(ADSB_POINT_URL, { cache: "no-store" });
      if (!res.ok) throw new Error("adsb " + res.status);
      const data = await res.json();
      const nowIso = new Date().toISOString();
      const live = (data.ac || [])
        .filter(isHemsAc)
        .filter((ac) => ac.lat != null && ac.lon != null && ac.lat >= 54.45 && ac.lat <= 57.9 && ac.lon >= 7.7 && ac.lon <= 15.4)
        .map((ac) => hemsToIncident(ac, nowIso));
      state.hemsLive = live;
      state.hemsCors = true;
      hemsFailCount = 0;
      showUpdated();
      render({ fitMap: false });
    } catch (_) {
      hemsFailCount += 1;
      if (hemsFailCount >= 2) {
        state.hemsCors = false;
        if (hemsTimer) {
          clearInterval(hemsTimer);
          hemsTimer = null;
        }
        showUpdated();
      }
    }
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
        if (state.hemsCors !== false) pollHems();
      }
    });
    window.addEventListener("focus", () => loadData({ silent: true, fitMap: false }));
    if (!hemsTimer) {
      hemsTimer = setInterval(pollHems, HEMS_POLL_MS);
      pollHems();
    }
  }

  async function init() {
    state.categories = loadCategories();
    state.tips = loadTips();
    state.timeHours = loadTimeHours();
    state.showRoutine = localStorage.getItem(STORAGE_ROUTINE) === "1";
    state.nearRadiusKm = parseInt(localStorage.getItem(STORAGE_RADIUS) || "25", 10) || 25;
    bindUi();
    await loadData({ silent: false, fitMap: true });
    startAutoRefresh();
  }

  init();
})();

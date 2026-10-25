(() => {
  const config = window.TF2_CONFIG || {};
  const $ = (id) => document.getElementById(id);
  let allItems = [];
  let allObservations = [];
  let chart = null;

  const formatPrice = (price, currency) => {
    const n = Number(price);
    if (!Number.isFinite(n)) return "—";
    return `${n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 6})} ${currency || "USD"}`;
  };
  const formatDate = (date) => {
    if (!date) return "—";
    const d = new Date(date);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
  };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[c]);

  function setStatus(text, ready = false) {
    $("connection").textContent = text;
    $("connection").style.borderColor = ready ? "#456d43" : "#5a5a3a";
  }

  function renderTable() {
    const term = $("search").value.trim().toLowerCase();
    const rows = allItems.filter((item) =>
      `${item.item_name} ${item.source} ${item.kind}`.toLowerCase().includes(term)
    );
    const body = $("itemsTable");
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="5" class="empty">${allItems.length ? "No hay coincidencias." : "No hay observaciones registradas todavía."}</td></tr>`;
      return;
    }
    body.innerHTML = rows.map((item) => {
      const latest = allObservations.find((o) => Number(o.item_id) === Number(item.id));
      const name = item.item_url
        ? `<a href="${escapeHtml(item.item_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.item_name)}</a>`
        : escapeHtml(item.item_name);
      return `<tr>
        <td>${name}</td>
        <td>${escapeHtml(item.source)}</td>
        <td><span class="type-pill">${item.kind === "buy_order" ? "Buy order" : "Venta"}</span></td>
        <td class="price">${latest ? formatPrice(latest.price, latest.currency) : "—"}</td>
        <td>${latest ? formatDate(latest.observed_at) : "—"}</td>
      </tr>`;
    }).join("");
  }

  function renderSelect() {
    const select = $("itemSelect");
    const previous = select.value;
    select.innerHTML = `<option value="">Selecciona un artículo</option>` + allItems.map((i) =>
      `<option value="${Number(i.id)}">${escapeHtml(i.item_name)} · ${escapeHtml(i.source)} · ${escapeHtml(i.kind)}</option>`
    ).join("");
    if (allItems.some((i) => String(i.id) === previous)) select.value = previous;
  }

  function renderChart() {
    const id = Number($("itemSelect").value);
    const item = allItems.find((i) => Number(i.id) === id);
    const points = allObservations
      .filter((o) => Number(o.item_id) === id)
      .sort((a, b) => new Date(a.observed_at) - new Date(b.observed_at));
    if (chart) chart.destroy();
    if (!item || !points.length || !window.Chart) {
      $("chartMessage").textContent = "Selecciona un artículo con observaciones para ver su evolución.";
      return;
    }
    $("chartMessage").textContent = `${points.length} observación(es) para ${item.item_name}.`;
    chart = new Chart($("priceChart"), {
      type: "line",
      data: {
        labels: points.map((p) => new Date(p.observed_at).toLocaleString()),
        datasets: [{
          label: `Precio (${points[0].currency || "USD"})`,
          data: points.map((p) => Number(p.price)),
          borderColor: "#a4f06b",
          backgroundColor: "rgba(164,240,107,.12)",
          pointRadius: 3,
          pointBackgroundColor: "#a4f06b",
          borderWidth: 2,
          fill: true,
          tension: .25
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#c2cfdf" } } },
        scales: {
          x: { ticks: { color: "#8e9bad", maxTicksLimit: 7 }, grid: { color: "#2a313d" } },
          y: { ticks: { color: "#8e9bad" }, grid: { color: "#2a313d" } }
        }
      }
    });
  }

  async function loadData() {
    if (!config.SUPABASE_URL || !config.SUPABASE_ANON_KEY || !window.supabase) {
      setStatus("Configuración pendiente");
      $("monitorState").textContent = "Pendiente";
      $("tableMessage").textContent = "Añade la URL y la clave pública anon de Supabase en config.js. No uses la clave service_role aquí.";
      return;
    }
    try {
      const client = window.supabase.createClient(config.SUPABASE_URL, config.SUPABASE_ANON_KEY);
      setStatus("Conectando…");
      const [itemsResult, obsResult] = await Promise.all([
        client.from("tf2_items").select("id,item_name,source,kind,item_url,created_at").order("item_name"),
        client.from("price_observations").select("id,item_id,price,currency,observed_at").order("observed_at", {ascending:false}).limit(5000)
      ]);
      if (itemsResult.error) throw itemsResult.error;
      if (obsResult.error) throw obsResult.error;
      allItems = itemsResult.data || [];
      allObservations = obsResult.data || [];
      const latestByItem = new Map();
      for (const obs of allObservations) {
        if (!latestByItem.has(Number(obs.item_id))) latestByItem.set(Number(obs.item_id), obs);
      }
      allObservations = allObservations;
      // Keep latest observation per item in the main table.
      const originalFind = allObservations.find.bind(allObservations);
      allObservations.find = (callback, thisArg) => originalFind(callback, thisArg);
      $("itemCount").textContent = String(allItems.length);
      $("observationCount").textContent = String(allObservations.length);
      const newest = allObservations.reduce((max, o) => Math.max(max, new Date(o.observed_at).getTime() || 0), 0);
      $("lastUpdated").textContent = newest ? formatDate(newest) : "Sin datos";
      $("monitorState").textContent = "Conectado";
      setStatus("Base de datos conectada", true);
      renderTable();
      renderSelect();
      renderChart();
    } catch (error) {
      console.error(error);
      setStatus("Error de conexión");
      $("tableMessage").textContent = "No se pudo leer Supabase. Comprueba la URL, la clave pública y las políticas RLS.";
    }
  }

  // Render latest observation correctly even though history is sorted newest-first.
  const originalRenderTable = renderTable;
  $("search").addEventListener("input", originalRenderTable);
  $("itemSelect").addEventListener("change", renderChart);
  loadData();
})();

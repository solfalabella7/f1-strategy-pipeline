// Ventana de boxes · lógica de la página.
// Los gráficos son especificaciones de Altair (generadas por build_app.py) que se
// dibujan con vega-embed. Los controles sólo cambian el valor de parámetros
// declarados en Altair (umbral, temporada, contexto, piloto, selección) o cargan
// los datos con nombre de cada gráfico.
import { predecir } from "./modelo.js";

const SPECS = JSON.parse(document.getElementById("specs").textContent);
const CFG = JSON.parse(document.getElementById("config").textContent);
const ORDEN = CFG.orden;
const fmt = (x, d = 0) => new Intl.NumberFormat("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d }).format(x);
const pct = (x, d = 0) => `${fmt(100 * x, d)} %`;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const LOCALE = { decimal: ",", thousands: ".", grouping: [3], currency: ["$", ""] };
const OPC = { actions: false, renderer: "svg", formatLocale: LOCALE, tooltip: { theme: "custom" }, logLevel: vega.Error };
const vistas = {};

async function dibujar(id, clave, nombre = clave) {
  const el = document.getElementById(id);
  if (!el || vistas[nombre]) return vistas[nombre];
  const r = await vegaEmbed(el, SPECS[clave], OPC);
  vistas[nombre] = r.view;
  return r.view;
}

// ------------------------------------------------------------------ navegación por sectores
// Cada sección es un sector: la barra se llena mientras se recorre (rojo) y queda en lima al completarlo.
function navegacion() {
  const enlaces = $$(".sectores a");
  const secciones = enlaces.map((a) => document.querySelector(a.getAttribute("href")));
  const actualizar = () => {
    const y = 120;
    enlaces.forEach((a, i) => {
      const s = secciones[i];
      if (!s) return;
      const r = s.getBoundingClientRect();
      const avance = Math.min(1, Math.max(0, (y - r.top) / Math.max(1, r.height)));
      a.querySelector(".s-barra i").style.width = `${avance * 100}%`;
      a.classList.toggle("activo", r.top <= y && r.bottom > y);
      a.classList.toggle("completo", r.bottom <= y);
    });
  };
  addEventListener("scroll", actualizar, { passive: true });
  addEventListener("resize", actualizar);
  actualizar();
}

// ------------------------------------------------------------------ movimiento
const SIN_MOVIMIENTO = matchMedia("(prefers-reduced-motion: reduce)").matches;

// Números que cuentan hasta su valor la primera vez que aparecen; el texto final es siempre el real.
function contadores() {
  const animar = (el) => {
    const final = el.dataset.contar;
    const m = final.match(/[\d.]+(,\d+)?/);
    if (!m || SIN_MOVIMIENTO) return;
    const objetivo = Number(m[0].replace(/\./g, "").replace(",", "."));
    const decimales = m[1] ? m[1].length - 1 : 0;
    const t0 = performance.now();
    const paso = (t) => {
      const k = Math.min(1, (t - t0) / 1100);
      el.textContent = final.replace(m[0], fmt(objetivo * (1 - Math.pow(1 - k, 3)), decimales));
      if (k < 1) requestAnimationFrame(paso); else el.textContent = final;
    };
    requestAnimationFrame(paso);
  };
  const io = new IntersectionObserver((entradas) => entradas.forEach((e) => {
    if (e.isIntersecting) { io.unobserve(e.target); animar(e.target); }
  }), { threshold: 0.6 });
  $$("[data-contar]").forEach((el) => io.observe(el));
}

// Bloques que aparecen al entrar en pantalla.
function aparecer() {
  if (SIN_MOVIMIENTO) return;
  const els = $$(".seccion-cabeza, .pantalla, .telemetria, .pipeline, .flujo, .mini-kpis, .que-mirar, .controles, .panel, .proba-grid");
  els.forEach((el) => el.classList.add("reveal"));
  const io = new IntersectionObserver((entradas) => entradas.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("visible"); io.unobserve(e.target); }
  }), { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
  els.forEach((el) => io.observe(el));
}

// Relleno del deslizador de umbral (pista cian hasta el valor elegido).
function rellenoUmbral() {
  const r = $("#c-umbral");
  const pintar = () => r.style.setProperty("--p", `${(100 * (r.value - r.min)) / (r.max - r.min)}%`);
  r.addEventListener("input", pintar);
  pintar();
  return pintar;
}

// ------------------------------------------------------------------ tallo
async function tallo() {
  await Promise.all([dibujar("g-datos", "datos"), dibujar("g-hallazgo", "hallazgo"), dibujar("g-modelo", "modelo")]);
  // Los gráficos dentro de «Cómo lo sabemos» se dibujan al abrir (necesitan ancho).
  const enDesplegable = {
    "g-h1": "h1", "g-familias-pit": "familias_pit", "g-familias-comp": "familias_comp", "g-umbral": "umbral",
    "g-matriz": "matriz", "g-imp-pit": "imp_pit", "g-imp-comp": "imp_comp", "g-pr": "pr",
    "g-distancias": "distancias", "g-mdi-pit": "mdi_pit", "g-mdi-comp": "mdi_comp",
  };
  $$("details.como").forEach((det) => det.addEventListener("toggle", () => {
    if (!det.open) return;
    $$(".grafico", det).forEach((fig) => enDesplegable[fig.id] && dibujar(fig.id, enDesplegable[fig.id]));
  }));
}

// ------------------------------------------------------------------ Explorá
const estado = { temporada: 2025, contexto: "Todas", umbral: CFG.umbral, carrera: null, filas: [], piloto: "", sel: null };
let paradas = [];

function carrerasDeTemporada() {
  return CFG.carreras.filter((c) => estado.temporada === 0 || c.temporada === estado.temporada);
}

function resumirVista() {
  const vis = paradas.filter((p) => (estado.temporada === 0 || p.temporada === estado.temporada)
    && (estado.contexto === "Todas" || p.contexto === estado.contexto));
  const con = vis.filter((p) => p.puntaje >= estado.umbral).length;
  const carreras = new Set(vis.map((p) => p.sk)).size;
  $("#resumen-vista").innerHTML = vis.length
    ? `En la vista: <strong>${fmt(vis.length)}</strong> paradas reales de <strong>${carreras}</strong> carreras; el modelo tenía la alarma encendida en <strong>${fmt(con)}</strong> (<strong>${pct(con / vis.length)}</strong>) con umbral ${fmt(estado.umbral, 3)}.`
    : "No hay paradas con esos filtros.";
}

function llenarCarreras() {
  const sel = $("#c-carrera");
  const lista = carrerasDeTemporada();
  sel.innerHTML = lista.map((c) => `<option value="${c.sk}">${c.nombre} · ${c.paradas} paradas</option>`).join("");
  if (!lista.some((c) => c.sk === estado.carrera)) cargarCarrera(lista[0].sk);
  else sel.value = estado.carrera;
}

// Los archivos de carrera vienen por columnas; se arma una fila por vuelta.
function expandir(datos) {
  const vueltas = datos.filas.map((a) => {
    const f = {};
    datos.columnas.forEach((c, i) => { f[c] = a[i]; });
    const [nombre, equipo, orden, numero] = datos.pilotos[f.piloto];
    Object.assign(f, { nombre, team_name: equipo, orden_piloto: orden, circuit_short_name: datos.circuito,
      lap_number: f.vuelta, id: `${datos.sk}-${numero}-${f.vuelta}`, para: Boolean(f.para), sc: Boolean(f.sc) });
    const total = f.n_soft + f.n_medium + f.n_hard + f.n_lluvia;
    for (const c of ["soft", "medium", "hard", "lluvia"]) f[`field_${c}_prev`] = total ? f[`n_${c}`] / total : null;
    return f;
  });
  return { ...datos, vueltas };
}

async function cargarCarrera(sk) {
  estado.carrera = Number(sk);
  $("#c-carrera").value = String(sk);
  const meta = CFG.carreras.find((c) => c.sk === estado.carrera);
  const resp = await fetch(`datos/carreras/${sk}.json`);
  const datos = expandir(await resp.json());
  if (estado.carrera !== Number(sk)) return; // llegó tarde: el usuario ya eligió otra
  estado.filas = datos.vueltas;
  $("#t-carrera").textContent = meta.nombre;
  $("#i-origen").textContent = datos.origen === "test"
    ? "Test 2025 · modelo final, que no vio esta temporada"
    : "Validación cruzada · modelo que no vio esta carrera";
  const sp = $("#c-piloto");
  sp.innerHTML = '<option value="">Todos</option>' + meta.pilotos.map(([a, n]) => `<option value="${a}">${n}</option>`).join("");
  estado.piloto = "";
  const v = await dibujar("g-carrera", "carrera");
  await v.signal("piloto", "").signal("seleccion", "").data("carrera", estado.filas).runAsync();
  cerrarDetalle();
}

function cerrarDetalle() {
  estado.sel = null;
  $("#detalle").hidden = true;
  $("#detalle-vacio").hidden = false;
  vistas.carrera && vistas.carrera.signal("seleccion", "").runAsync();
}

function valorVariable(clave, v) {
  if (v === null || v === undefined) return "sin dato";
  if (clave.startsWith("used_")) return v ? "sí" : "no";
  if (clave === "rainfall_prev") return v ? "sí" : "no";
  if (clave.startsWith("field_")) return pct(v);
  if (clave.endsWith("temperature_prev") || clave === "humidity_prev") return fmt(v, 1);
  if (clave === "compound_prev") return `<span class="chip chip-${String(v).toLowerCase()}">${v}</span>`;
  return typeof v === "number" ? fmt(v) : v;
}

async function mostrarDetalle(fila) {
  estado.sel = fila;
  const meta = CFG.carreras.find((c) => c.sk === estado.carrera);
  $("#detalle").hidden = false;
  $("#detalle-vacio").hidden = true;
  $("#d-volanta").textContent = `${meta.nombre} · ${fila.piloto}`;
  $("#d-titulo").textContent = `${fila.nombre}, vuelta ${fila.vuelta}`;
  const alarma = fila.puntaje >= estado.umbral;
  const acierto = fila.para ? (alarma ? "anticipada" : "no anticipada") : (alarma ? "falsa alarma" : "sin alarma, correcto");
  $("#d-resultado").innerHTML = [
    ["¿Paró en esta vuelta?", fila.para ? `sí, montó <span class="chip chip-${fila.objetivo.toLowerCase()}">${fila.objetivo}</span>` : "no"],
    ["Puntaje de parada", fmt(fila.puntaje, 3)],
    [`Alarma (umbral ${fmt(estado.umbral, 3)})`, alarma ? '<span class="tag-si">encendida</span>' : '<span class="tag-no">apagada</span>'],
    ["Lectura", acierto],
    ["Neumático que propone", `<span class="chip chip-${fila.comp_pred.toLowerCase()}">${fila.comp_pred}</span>`],
    ["Safety car en esta vuelta", fila.sc ? "sí (el modelo no lo ve)" : "no"],
  ].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
  const claves = ["lap_number", "compound_prev", "tyre_age_prev", "stops_before", "position_prev", "used_soft", "used_medium",
    "used_hard", "field_soft_prev", "field_medium_prev", "field_hard_prev", "field_lluvia_prev", "track_temperature_prev",
    "air_temperature_prev", "humidity_prev", "rainfall_prev", "team_name", "circuit_short_name"];
  $("#d-variables").innerHTML = claves.map((k) => `<dt>${CFG.etiquetas[k]}</dt><dd>${valorVariable(k, fila[k])}</dd>`).join("");
  const vp = await dibujar("g-prob-explora", "prob_explora");
  await vp.data("prob_explora", ORDEN.map((c, i) => ({ compuesto: c, p: fila.p[i] }))).runAsync();
  await mostrarTrayectoria(fila.piloto);
  vistas.carrera.signal("seleccion", fila.id).runAsync();
}

async function mostrarTrayectoria(piloto) {
  const filas = estado.filas.filter((f) => f.piloto === piloto);
  if (!filas.length) return;
  $("#d-tray-titulo").textContent = `Puntaje vuelta a vuelta · ${filas[0].nombre}`;
  const vt = await dibujar("g-trayectoria", "trayectoria");
  await vt.signal("umbral", estado.umbral).data("trayectoria", filas).runAsync();
}

async function explora() {
  paradas = await (await fetch("datos/paradas.json")).json();
  const vp = await dibujar("g-panorama", "panorama");
  await vp.data("paradas", paradas).runAsync();
  vp.addEventListener("click", (ev, item) => {
    const c = item && item.datum && item.datum.carrera;
    const meta = c && CFG.carreras.find((x) => x.nombre === c);
    if (meta) { cargarCarrera(meta.sk); $("#c-carrera").scrollIntoView({ behavior: "smooth", block: "center" }); }
  });

  $$("#c-temporada button").forEach((b) => b.addEventListener("click", async () => {
    $$("#c-temporada button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    estado.temporada = Number(b.dataset.valor);
    await vp.signal("temporada", estado.temporada).runAsync();
    resumirVista();
    llenarCarreras();
  }));
  $("#c-contexto").addEventListener("change", async (e) => {
    estado.contexto = e.target.value;
    await vp.signal("contexto", estado.contexto).runAsync();
    resumirVista();
  });
  const fijarUmbral = async (u) => {
    estado.umbral = u;
    $("#c-umbral").value = u;
    pintarUmbral();
    $("#o-umbral").textContent = fmt(u, 3);
    await Promise.all(["panorama", "carrera", "trayectoria"].filter((k) => vistas[k])
      .map((k) => vistas[k].signal("umbral", u).runAsync()));
    resumirVista();
    if (estado.sel) mostrarDetalle(estado.sel);
  };
  $("#c-umbral").addEventListener("input", (e) => fijarUmbral(Number(e.target.value)));
  $("#b-umbral").addEventListener("click", () => fijarUmbral(CFG.umbral));
  $("#c-carrera").addEventListener("change", (e) => cargarCarrera(e.target.value));
  $("#c-piloto").addEventListener("change", async (e) => {
    estado.piloto = e.target.value;
    await vistas.carrera.signal("piloto", estado.piloto).runAsync();
    if (estado.piloto) {
      const filas = estado.filas.filter((f) => f.piloto === estado.piloto);
      mostrarDetalle(filas.find((f) => f.para) || filas[0]);
    } else cerrarDetalle();
  });
  const vc = await dibujar("g-carrera", "carrera");
  vc.addEventListener("click", (ev, item) => {
    const id = item && item.datum && item.datum.id;
    const fila = id && estado.filas.find((f) => f.id === id);
    if (fila) mostrarDetalle(fila);
  });
  $("#b-probar").addEventListener("click", async () => {
    if (!estado.sel) return;
    cambiarModo("real");
    await elegirCarrera(estado.carrera, estado.sel.piloto, estado.sel.vuelta);
    document.getElementById("proba").scrollIntoView({ behavior: "smooth" });
  });
  resumirVista();
  llenarCarreras();
}

// ------------------------------------------------------------------ Probá el modelo
// Dos modos. «Vuelta real»: la predicción guardada de un modelo que no vio esa carrera, contra lo que pasó.
// «Mi escenario»: el formulario; el navegador corre los dos random forest exportados (modelo.js).
let MOD_PIT = null, MOD_COMP = null;
const form = () => $("#formulario");
const ENTEROS = ["lap_number", "tyre_age_prev", "position_prev", "stops_before", "n_soft", "n_medium", "n_hard", "n_lluvia"];
const DECIMALES = ["track_temperature_prev", "air_temperature_prev", "humidity_prev"];
const CHECKS = ["used_soft", "used_medium", "used_hard", "rainfall_prev"];
const SELECTS = ["circuit_short_name", "team_name", "compound_prev"];
let origenCaso = null;
const sim = { modo: "real", sk: null, datos: null, piloto: null, filas: [], i: 0 };
const cacheCarreras = {};
async function datosCarrera(sk) {
  if (!cacheCarreras[sk]) cacheCarreras[sk] = expandir(await (await fetch(`datos/carreras/${sk}.json`)).json());
  return cacheCarreras[sk];
}
const chip = (c) => `<span class="chip chip-${String(c).toLowerCase()}">${c}</span>`;

// ---------- resultado (común a los dos modos)
async function pintarResultado({ p, probs, avisos, real }) {
  const res = $("#resultado");
  res.classList.remove("invalido");
  const mejor = probs.reduce((a, b) => (b.p > a.p ? b : a));
  const alarma = p >= CFG.umbral;
  $("#r-veredicto").textContent = alarma ? "Alarma: se abrió la ventana de parada" : "Sin alarma: sigue en pista";
  $("#r-veredicto").classList.toggle("si", alarma);
  $("#r-para").textContent = alarma ? "SÍ, PARA" : "NO, SIGUE";
  $("#r-d-para").classList.toggle("activa", alarma);
  $("#r-para-det").textContent = `puntaje ${fmt(p, 3)} · umbral ${fmt(CFG.umbral, 3)}`;
  $("#r-comp").innerHTML = chip(mejor.compuesto);
  $("#r-comp-det").textContent = `${pct(mejor.p)} de probabilidad${alarma ? "" : " (solo cuenta si para)"}`;
  $("#r-texto").textContent = alarma
    ? `El puntaje supera el umbral: el modelo diría que se abrió la ventana de parada y que el neumático más probable es ${mejor.compuesto}.`
    : `El puntaje queda debajo del umbral: el modelo diría que todavía no es momento de parar. Si igual parara, el neumático más probable sería ${mejor.compuesto}.`;
  const comp = $("#r-comparacion");
  comp.hidden = !real;
  if (real) {
    comp.className = `comparacion ${real.clase}`;
    $("#r-real-pasado").innerHTML = real.pasado;
    $("#r-juicio").innerHTML = real.juicio;
  }
  $("#r-avisos").innerHTML = avisos.map((a) => `<li>${a}</li>`).join("");
  const [vs, vb] = await Promise.all([dibujar("g-puntaje", "puntaje"), dibujar("g-prob-proba", "prob_proba")]);
  await Promise.all([vs.data("puntaje", [{ p }]).runAsync(), vb.data("prob_proba", probs).runAsync()]);
}

function avisosDe(x, extra = []) {
  const T = CFG.textos;
  const a = [];
  const lluviaPelo = x.field_lluvia_prev > 0;
  if (x.rainfall_prev || lluviaPelo || ["INTERMEDIATE", "WET"].includes(x.compound_prev)) a.push(T.aviso_lluvia);
  if (["INTERMEDIATE", "WET"].includes(x.compound_prev) && x.field_lluvia_prev >= 0.5) a.push(T.aviso_secado);
  return a.concat(extra);
}

// ---------- modo 1: vuelta real
function juicioReal(f) {
  const alarma = f.puntaje >= CFG.umbral;
  const mejor = ORDEN[f.p.indexOf(Math.max(...f.p))];
  const pasado = f.para ? `Paró en esta vuelta y montó ${chip(f.objetivo)}` : "No paró en esta vuelta: siguió en pista";
  if (f.para && alarma) {
    const ok = mejor === f.objetivo;
    return { clase: ok ? "ok" : "parcial", pasado,
      juicio: ok ? "<b>Acierto completo.</b> Tenía la alarma encendida y eligió el mismo neumático."
                 : `<b>Anticipó la parada, pero no el neumático:</b> propuso ${chip(mejor)}.` };
  }
  if (f.para && !alarma) {
    const motivo = f.sc ? " Fue una parada con safety car, algo que el modelo no ve."
      : f.objetivo === "LLUVIA" ? " Fue un cambio a neumáticos de lluvia: el modelo casi nunca los anticipa."
      : ["INTERMEDIATE", "WET"].includes(f.compound_prev) ? " Venía con neumáticos de lluvia y pasó a seco: la pista se estaba secando, una señal que el modelo no tiene." : "";
    return { clase: "error", pasado, juicio: `<b>Parada no anticipada.</b> El modelo no tenía la alarma encendida.${motivo}` };
  }
  if (!f.para && alarma) {
    const siguiente = sim.filas.find((v) => v.vuelta > f.vuelta && v.para);
    const k = siguiente ? siguiente.vuelta - f.vuelta : null;
    const cuando = k === null ? "Este piloto no volvió a parar en la carrera (stint final largo)."
      : `La parada real llegó ${k} ${k === 1 ? "vuelta" : "vueltas"} después${k <= 10 ? ": la ventana estaba abierta, faltaba la vuelta exacta" : ""}.`;
    return { clase: k !== null && k <= 10 ? "parcial" : "error", pasado, juicio: `<b>Falsa alarma.</b> ${cuando}` };
  }
  return { clase: "ok", pasado, juicio: "<b>Correcto.</b> Sin alarma, y el piloto siguió en pista." };
}

function mostrarSituacion(f) {
  const tot = f.n_soft + f.n_medium + f.n_hard + f.n_lluvia;
  const barra = tot ? `<span class="peloton" role="img" aria-label="Pelotón: ${f.n_soft} SOFT, ${f.n_medium} MEDIUM, ${f.n_hard} HARD, ${f.n_lluvia} lluvia">${
    [["soft", f.n_soft], ["medium", f.n_medium], ["hard", f.n_hard], ["lluvia", f.n_lluvia]].filter(([, n]) => n)
      .map(([c, n]) => `<i class="pel-${c}" style="flex:${n}" title="${n} en ${c.toUpperCase()}"></i>`).join("")}</span>` : "sin dato";
  const usados = ["soft", "medium", "hard"].filter((c) => f[`used_${c}`]).map((c) => chip(c.toUpperCase())).join(" ") || "ninguno";
  const dato = (v, d = 0, suf = "") => (v === null || v === undefined ? "sin dato" : `${fmt(v, d)}${suf}`);
  $("#s-situacion").innerHTML = [
    ["Neumático", `${f.compound_prev ? chip(f.compound_prev) : "sin dato"} <b>${dato(f.tyre_age_prev)}</b> vueltas de uso`],
    ["Paradas ya hechas", `<b>${dato(f.stops_before)}</b>`],
    ["Compuestos ya usados", usados],
    ["Posición", `<b>${dato(f.position_prev)}</b>`],
    ["Pelotón en la vuelta anterior", barra],
    ["Clima", `pista ${dato(f.track_temperature_prev, 1, " °C")} · aire ${dato(f.air_temperature_prev, 1, " °C")} · humedad ${dato(f.humidity_prev, 0, " %")}${f.rainfall_prev ? " · <b>llueve</b>" : ""}`],
    ["Equipo · circuito", `${f.team_name} · ${f.circuit_short_name}`],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
}

async function mostrarVueltaReal() {
  const f = sim.filas[sim.i];
  if (!f) return;
  const meta = CFG.carreras.find((c) => c.sk === sim.sk);
  $("#s-vuelta").value = sim.i;
  $("#s-vuelta-n").textContent = `${f.vuelta} / ${sim.filas[sim.filas.length - 1].vuelta}`;
  $("#s-prev").disabled = sim.i === 0;
  $("#s-next").disabled = sim.i === sim.filas.length - 1;
  mostrarSituacion(f);
  $("#r-volanta").textContent = `${f.nombre} · ${meta.nombre} · vuelta ${f.vuelta}`;
  const probs = ORDEN.map((c, k) => ({ compuesto: c, p: f.p[k] }));
  const extra = f.sc ? [CFG.textos.aviso_sc] : [];
  await pintarResultado({ p: f.puntaje, probs, avisos: avisosDe(f, extra), real: juicioReal(f) });
  const vt = await dibujar("g-sim-tray", "trayectoria", "sim_tray");
  await vt.signal("vuelta_sel", f.vuelta).runAsync();
}

async function elegirPiloto(acr, vuelta = null) {
  sim.piloto = acr;
  $("#s-piloto").value = acr;
  sim.filas = sim.datos.vueltas.filter((v) => v.piloto === acr).sort((a, b) => a.vuelta - b.vuelta);
  $("#s-vuelta").max = sim.filas.length - 1;
  const k = vuelta === null ? sim.filas.findIndex((v) => v.para) : sim.filas.findIndex((v) => v.vuelta === vuelta);
  sim.i = Math.max(0, k);
  const vt = await dibujar("g-sim-tray", "trayectoria", "sim_tray");
  await vt.signal("umbral", CFG.umbral).data("trayectoria", sim.filas).runAsync();
  await mostrarVueltaReal();
}

async function elegirCarrera(sk, piloto = null, vuelta = null) {
  sim.sk = Number(sk);
  $("#s-carrera").value = String(sk);
  sim.datos = await datosCarrera(sk);
  const meta = CFG.carreras.find((c) => c.sk === sim.sk);
  $("#s-piloto").innerHTML = meta.pilotos.map(([a, n]) => `<option value="${a}">${n}</option>`).join("");
  await elegirPiloto(piloto && meta.pilotos.some(([a]) => a === piloto) ? piloto : meta.pilotos[0][0], vuelta);
}

async function sorprendeme() {
  const lista = CFG.carreras.filter((c) => c.temporada === 2025);
  const c = lista[Math.floor(Math.random() * lista.length)];
  const datos = await datosCarrera(c.sk);
  const paradas = datos.vueltas.filter((v) => v.para);
  const v = paradas[Math.floor(Math.random() * paradas.length)];
  await elegirCarrera(c.sk, v.piloto, v.vuelta);
}

function prepararModoReal() {
  const temporadas = [...new Set(CFG.carreras.map((c) => c.temporada))].sort((a, b) => b - a);
  $("#s-carrera").innerHTML = temporadas.map((t) => `<optgroup label="${t}${t === 2025 ? " · test" : " · validación cruzada"}">` +
    CFG.carreras.filter((c) => c.temporada === t).map((c) => `<option value="${c.sk}">${c.nombre}</option>`).join("") + "</optgroup>").join("");
  $("#s-carrera").addEventListener("change", (e) => elegirCarrera(e.target.value));
  $("#s-piloto").addEventListener("change", (e) => elegirPiloto(e.target.value));
  $("#s-vuelta").addEventListener("input", (e) => { sim.i = Number(e.target.value); mostrarVueltaReal(); });
  $("#s-prev").addEventListener("click", () => { if (sim.i > 0) { sim.i--; mostrarVueltaReal(); } });
  $("#s-next").addEventListener("click", () => { if (sim.i < sim.filas.length - 1) { sim.i++; mostrarVueltaReal(); } });
  $("#s-proxima").addEventListener("click", () => {
    const k = sim.filas.findIndex((v, j) => j > sim.i && v.para);
    sim.i = k >= 0 ? k : Math.max(0, sim.filas.findIndex((v) => v.para));
    mostrarVueltaReal();
  });
  $("#b-ejemplo").addEventListener("click", sorprendeme);
  $("#s-editar").addEventListener("click", () => {
    const f = sim.filas[sim.i];
    const meta = CFG.carreras.find((c) => c.sk === sim.sk);
    cargarEnFormulario(f, `${f.nombre} · ${meta.nombre} · vuelta ${f.vuelta}`, f.para ? `paró y montó ${f.objetivo}` : "no paró en esa vuelta");
    cambiarModo("propio");
  });
}

// ---------- modo 2: mi escenario
function prepararFormulario() {
  const f = form();
  for (const nombre of SELECTS) {
    f.elements[nombre].innerHTML = CFG.categorias[nombre].map((c) => `<option>${c}</option>`).join("");
  }
  for (const nombre of [...ENTEROS, ...DECIMALES]) {
    const r = nombre.startsWith("n_") ? { min: 0, max: CFG.rangos.autos.max } : CFG.rangos[nombre];
    f.elements[nombre].min = r.min;
    f.elements[nombre].max = r.max;
    f.elements[nombre].placeholder = `${fmt(r.min, DECIMALES.includes(nombre) ? 1 : 0)} a ${fmt(r.max, DECIMALES.includes(nombre) ? 1 : 0)}`;
  }
  f.addEventListener("input", (e) => {
    if (!e.target.name) return;
    if (origenCaso) origenCaso.modificado = true;
    evaluar();
  });
  f.addEventListener("change", (e) => { if (e.target.name) evaluar(); });
}

function cargarEnFormulario(fila, desc, real) {
  const f = form();
  for (const n of SELECTS) f.elements[n].value = fila[n];
  for (const n of ENTEROS) f.elements[n].value = fila[n] ?? "";
  for (const n of DECIMALES) f.elements[n].value = fila[n] === null || fila[n] === undefined ? "" : Math.round(fila[n] * 10) / 10;
  for (const n of CHECKS) f.elements[n].checked = Boolean(fila[n]);
  // Los decimales del clima se guardan con su valor exacto para reproducir la predicción del dataset.
  origenCaso = { desc, real, exacto: Object.fromEntries(DECIMALES.map((n) => [n, fila[n]])), modificado: false };
  if (sim.modo === "propio") evaluar();
}

function leerYValidar() {
  const f = form();
  const errores = [];
  const malos = new Set();
  const x = {};
  for (const n of SELECTS) {
    x[n] = f.elements[n].value;
    if (!CFG.categorias[n].includes(x[n])) { errores.push(`${CFG.etiquetas[n] || n}: valor que el modelo no vio.`); malos.add(n); }
  }
  const nombreCampo = (n) => (n.startsWith("n_") ? `Autos en ${n.slice(2).toUpperCase()}` : CFG.etiquetas[n]);
  for (const n of [...ENTEROS, ...DECIMALES]) {
    const txt = f.elements[n].value.trim();
    const r = n.startsWith("n_") ? { min: 0, max: CFG.rangos.autos.max } : CFG.rangos[n];
    if (txt === "") { errores.push(`${nombreCampo(n)}: falta el valor.`); malos.add(n); continue; }
    const v = Number(txt);
    if (!Number.isFinite(v)) { errores.push(`${nombreCampo(n)}: no es un número.`); malos.add(n); continue; }
    if (ENTEROS.includes(n) && !Number.isInteger(v)) { errores.push(`${nombreCampo(n)}: tiene que ser un número entero.`); malos.add(n); }
    if (v < r.min || v > r.max) {
      errores.push(`${nombreCampo(n)}: ${fmt(v, DECIMALES.includes(n) ? 1 : 0)} está fuera de lo que vio el modelo (${fmt(r.min, DECIMALES.includes(n) ? 1 : 0)} a ${fmt(r.max, DECIMALES.includes(n) ? 1 : 0)}).`);
      malos.add(n);
    }
    x[n] = v;
  }
  for (const n of CHECKS) x[n] = f.elements[n].checked ? 1 : 0;
  // Si no se tocó el clima de un caso real, se usa su valor exacto (el formulario lo muestra redondeado).
  if (origenCaso && origenCaso.exacto) {
    for (const n of DECIMALES) {
      const e = origenCaso.exacto[n];
      if (e !== null && e !== undefined && Math.round(e * 10) / 10 === x[n]) x[n] = e;
    }
  }
  // Coherencia entre campos: combinaciones imposibles en una carrera real.
  if (!malos.has("stops_before") && !malos.has("lap_number") && x.stops_before > x.lap_number - 1) {
    errores.push("Paradas ya hechas: no puede haber más paradas que vueltas completadas."); malos.add("stops_before");
  }
  // Combinaciones raras que sí aparecen en los datos: se avisan, no se bloquean.
  const raras = [];
  const R = CFG.raras;
  const frec = (n) => `aparece en ${fmt(n)} de ${fmt(R.total)} vueltas del dataset`;
  if (x.stops_before >= 1 && x.tyre_age_prev > x.lap_number + 5) raras.push(`Edad del neumático mayor que las vueltas corridas más 5: ${frec(R.edad)}.`);
  const seco = { SOFT: "used_soft", MEDIUM: "used_medium", HARD: "used_hard" };
  if (seco[x.compound_prev] && !x[seco[x.compound_prev]]) {
    errores.push(`Compuestos ya usados: si lleva ${x.compound_prev}, tiene que figurar como usado.`); malos.add(seco[x.compound_prev]);
  }
  const usados = x.used_soft + x.used_medium + x.used_hard;
  if (!malos.has("stops_before") && usados > x.stops_before + 1) raras.push(`Más compuestos usados que paradas + 1: ${frec(R.usados)}.`);
  const autos = ["n_soft", "n_medium", "n_hard", "n_lluvia"];
  if (autos.every((n) => !malos.has(n))) {
    const total = autos.reduce((s, n) => s + x[n], 0);
    if (total < CFG.rangos.autos.min || total > CFG.rangos.autos.max) {
      errores.push(`Pelotón: suman ${total} autos; el modelo vio entre ${CFG.rangos.autos.min} y ${CFG.rangos.autos.max}.`); autos.forEach((n) => malos.add(n));
    } else {
      const propio = { SOFT: "n_soft", MEDIUM: "n_medium", HARD: "n_hard", INTERMEDIATE: "n_lluvia", WET: "n_lluvia" }[x.compound_prev];
      if (propio && x[propio] < 1) raras.push(`Ningún auto del pelotón con el neumático del propio piloto: ${frec(R.propio)}.`);
      x.field_soft_prev = x.n_soft / total; x.field_medium_prev = x.n_medium / total;
      x.field_hard_prev = x.n_hard / total; x.field_lluvia_prev = x.n_lluvia / total;
    }
  }
  if (!malos.has("humidity_prev") && (x.humidity_prev < 0 || x.humidity_prev > 100)) { errores.push("Humedad: va de 0 a 100 %."); malos.add("humidity_prev"); }
  $$("#formulario [name]").forEach((el) => el.classList.toggle("campo-error", malos.has(el.name)));
  return { x, errores, raras };
}

async function evaluar() {
  if (!MOD_PIT || !MOD_COMP || sim.modo !== "propio") return;
  const { x, errores, raras } = leerYValidar();
  const caja = $("#errores");
  const res = $("#resultado");
  $("#r-volanta").textContent = "Lo que predice el modelo para tu escenario";
  $("#f-origen").textContent = origenCaso ? `${origenCaso.modificado ? "Modificado a partir de: " : "Partiste de: "}${origenCaso.desc}` : "";
  const real = $("#r-real");
  real.hidden = !origenCaso;
  if (origenCaso) real.textContent = `En la carrera real (${origenCaso.desc}): ${origenCaso.real}.`;
  if (errores.length) {
    caja.hidden = false;
    caja.innerHTML = `<p>Revisá ${errores.length === 1 ? "este dato" : "estos datos"} antes de predecir:</p><ul>${errores.map((e) => `<li>${e}</li>`).join("")}</ul>`;
    res.classList.add("invalido");
    $("#r-veredicto").textContent = "Datos no válidos";
    $("#r-veredicto").classList.remove("si");
    $("#r-para").textContent = "—"; $("#r-comp").textContent = "—"; $("#r-para-det").textContent = ""; $("#r-comp-det").textContent = "";
    $("#r-comparacion").hidden = true;
    $("#r-texto").textContent = `Hay ${errores.length === 1 ? "un dato marcado" : `${errores.length} datos marcados`} en el formulario. El modelo no predice con valores que nunca vio ni con combinaciones imposibles.`;
    $("#r-avisos").innerHTML = "";
    return;
  }
  caja.hidden = true;
  const fila = {};
  for (const n of [...MOD_PIT.numericas, ...MOD_PIT.categoricas]) fila[n] = x[n];
  const p = predecir(MOD_PIT, fila);
  const pc = predecir(MOD_COMP, fila);
  const probs = ORDEN.map((c) => ({ compuesto: c, p: pc[MOD_COMP.clases.indexOf(c)] }));
  const extra = [CFG.textos.aviso_sc];
  if (p >= CFG.umbral) extra.unshift(CFG.textos.aviso_alarma);
  for (const r of raras) extra.push(`Combinación poco común. ${r} La predicción se apoya en pocos casos parecidos.`);
  await pintarResultado({ p, probs, avisos: avisosDe(x, extra), real: null });
}

// ---------- cambio de modo
function cambiarModo(modo) {
  sim.modo = modo;
  $$(".modos button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.modo === modo)));
  $("#modo-real").hidden = modo !== "real";
  $("#formulario").hidden = modo !== "propio";
  $("#r-real").hidden = true;
  if (modo === "real") mostrarVueltaReal(); else evaluar();
}

async function proba() {
  [MOD_PIT, MOD_COMP] = await Promise.all([
    fetch("datos/modelo_parada.json").then((r) => r.json()),
    fetch("datos/modelo_compuesto.json").then((r) => r.json()),
  ]);
  prepararFormulario();
  prepararModoReal();
  $$(".modos button").forEach((b) => b.addEventListener("click", () => cambiarModo(b.dataset.modo)));
  const c = CFG.caso_inicial;
  cargarEnFormulario(c, c._desc, c._real);
  const vt = await dibujar("g-sim-tray", "trayectoria", "sim_tray");
  vt.addEventListener("click", (ev, item) => {
    const v = item && item.datum && item.datum.vuelta;
    const k = sim.filas.findIndex((f) => f.vuelta === v);
    if (k >= 0) { sim.i = k; mostrarVueltaReal(); }
  });
  await elegirCarrera(c._sk, c._piloto, c._vuelta);
}

// ------------------------------------------------------------------ inicio
navegacion();
aparecer();
contadores();
const pintarUmbral = rellenoUmbral();
// Se espera a la tipografía para que Vega mida bien los rótulos de los ejes.
await document.fonts.ready;
tallo();
explora().catch((e) => { console.error(e); $("#resumen-vista").textContent = "No se pudieron cargar los datos de exploración."; });
proba().catch((e) => { console.error(e); $("#r-veredicto").textContent = "No se pudo cargar el modelo."; });

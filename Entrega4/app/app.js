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

async function dibujar(id, clave) {
  const el = document.getElementById(id);
  if (!el || vistas[clave]) return vistas[clave];
  const r = await vegaEmbed(el, SPECS[clave], OPC);
  vistas[clave] = r.view;
  return r.view;
}

// ------------------------------------------------------------------ navegación
function navegacion() {
  const enlaces = $$(".barra-enlaces a");
  const secciones = enlaces.map((a) => document.querySelector(a.getAttribute("href")));
  const barra = $(".progreso-barra");
  const alDesplazar = () => {
    const h = document.documentElement;
    barra.style.width = `${(100 * h.scrollTop) / Math.max(1, h.scrollHeight - h.clientHeight)}%`;
    let activo = -1;
    secciones.forEach((s, i) => { if (s && s.getBoundingClientRect().top < 140) activo = i; });
    enlaces.forEach((a, i) => a.classList.toggle("activo", i === activo));
  };
  addEventListener("scroll", alDesplazar, { passive: true });
  alDesplazar();
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
  $("#b-probar").addEventListener("click", () => {
    if (!estado.sel) return;
    const meta = CFG.carreras.find((c) => c.sk === estado.carrera);
    cargarEnFormulario(estado.sel, `${estado.sel.nombre} · ${meta.nombre} · vuelta ${estado.sel.vuelta}`,
      estado.sel.para ? `paró y montó ${estado.sel.objetivo}` : "no paró en esa vuelta");
    document.getElementById("proba").scrollIntoView({ behavior: "smooth" });
  });
  resumirVista();
  llenarCarreras();
}

// ------------------------------------------------------------------ Probá el modelo
let MOD_PIT = null, MOD_COMP = null;
const form = () => $("#formulario");
const ENTEROS = ["lap_number", "tyre_age_prev", "position_prev", "stops_before", "n_soft", "n_medium", "n_hard", "n_lluvia"];
const DECIMALES = ["track_temperature_prev", "air_temperature_prev", "humidity_prev"];
const CHECKS = ["used_soft", "used_medium", "used_hard", "rainfall_prev"];
const SELECTS = ["circuit_short_name", "team_name", "compound_prev"];
let origenCaso = null;

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
  f.addEventListener("input", () => { if (origenCaso) { origenCaso.modificado = true; } evaluar(); });
  f.addEventListener("change", evaluar);
  $("#b-ejemplo").addEventListener("click", ejemploAlAzar);
}

function cargarEnFormulario(fila, desc, real) {
  const f = form();
  for (const n of SELECTS) f.elements[n].value = fila[n];
  for (const n of ENTEROS) f.elements[n].value = fila[n] ?? "";
  for (const n of DECIMALES) f.elements[n].value = fila[n] === null || fila[n] === undefined ? "" : Math.round(fila[n] * 10) / 10;
  for (const n of CHECKS) f.elements[n].checked = Boolean(fila[n]);
  // Los decimales del clima se guardan con su valor exacto para reproducir la predicción del dataset.
  origenCaso = { desc, real, exacto: Object.fromEntries(DECIMALES.map((n) => [n, fila[n]])), modificado: false };
  evaluar();
}

async function ejemploAlAzar() {
  const lista = CFG.carreras.filter((c) => c.temporada === 2025);
  const c = lista[Math.floor(Math.random() * lista.length)];
  const datos = expandir(await (await fetch(`datos/carreras/${c.sk}.json`)).json());
  const candidatas = datos.vueltas.filter((v) => v.tyre_age_prev !== null && v.position_prev !== null
    && v.track_temperature_prev !== null && CFG.categorias.team_name.includes(v.team_name));
  // Se prueban vueltas al azar hasta encontrar una dentro de lo que vio el modelo (2023-2024).
  for (let intento = 0; intento < 200; intento++) {
    const v = candidatas[Math.floor(Math.random() * candidatas.length)];
    cargarEnFormulario(v, `${v.nombre} · ${c.nombre} · vuelta ${v.vuelta}`, v.para ? `paró y montó ${v.objetivo}` : "no paró en esa vuelta");
    if (!leerYValidar().errores.length) return;
  }
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
  if (!MOD_PIT || !MOD_COMP) return;
  const { x, errores, raras } = leerYValidar();
  const caja = $("#errores");
  const res = $("#resultado");
  $("#f-origen").textContent = origenCaso ? `${origenCaso.modificado ? "Modificado a partir de: " : "Caso real: "}${origenCaso.desc}` : "";
  const real = $("#r-real");
  real.hidden = !origenCaso || origenCaso.modificado;
  if (origenCaso) real.textContent = `En la carrera real: ${origenCaso.real}.`;
  if (errores.length) {
    caja.hidden = false;
    caja.innerHTML = `<p>Revisá ${errores.length === 1 ? "este dato" : "estos datos"} antes de predecir:</p><ul>${errores.map((e) => `<li>${e}</li>`).join("")}</ul>`;
    res.classList.add("invalido");
    $("#r-veredicto").textContent = "Datos no válidos";
    $("#r-veredicto").classList.remove("si");
    $("#r-texto").textContent = `Hay ${errores.length === 1 ? "un dato marcado" : `${errores.length} datos marcados`} en el formulario. El modelo no predice con valores que nunca vio ni con combinaciones imposibles.`;
    $("#r-avisos").innerHTML = "";
    return;
  }
  caja.hidden = true;
  res.classList.remove("invalido");
  const fila = {};
  for (const n of [...MOD_PIT.numericas, ...MOD_PIT.categoricas]) fila[n] = x[n];
  const p = predecir(MOD_PIT, fila);
  const pc = predecir(MOD_COMP, fila);
  const probs = ORDEN.map((c) => ({ compuesto: c, p: pc[MOD_COMP.clases.indexOf(c)] }));
  const mejor = probs.reduce((a, b) => (b.p > a.p ? b : a));
  const alarma = p >= CFG.umbral;
  $("#r-veredicto").textContent = alarma ? `Alarma: se abrió la ventana, monta ${mejor.compuesto}` : "Sin alarma: sigue en pista";
  $("#r-veredicto").classList.toggle("si", alarma);
  $("#r-texto").textContent = alarma
    ? `Puntaje ${fmt(p, 3)}, por encima del umbral ${fmt(CFG.umbral, 3)}. Si para, el neumático más probable es ${mejor.compuesto} (${pct(mejor.p)}).`
    : `Puntaje ${fmt(p, 3)}, por debajo del umbral ${fmt(CFG.umbral, 3)}. Si igual parara, el neumático más probable sería ${mejor.compuesto} (${pct(mejor.p)}).`;
  const avisos = [];
  const T = CFG.textos;
  if (alarma) avisos.push(T.aviso_alarma);
  if (x.rainfall_prev || x.field_lluvia_prev > 0 || ["INTERMEDIATE", "WET"].includes(x.compound_prev)) avisos.push(T.aviso_lluvia);
  if (["INTERMEDIATE", "WET"].includes(x.compound_prev) && x.field_lluvia_prev >= 0.5) avisos.push(T.aviso_secado);
  avisos.push(T.aviso_sc);
  for (const r of raras) avisos.push(`Combinación poco común. ${r} La predicción se apoya en pocos casos parecidos.`);
  $("#r-avisos").innerHTML = avisos.map((a) => `<li>${a}</li>`).join("");
  const [vs, vb] = await Promise.all([dibujar("g-puntaje", "puntaje"), dibujar("g-prob-proba", "prob_proba")]);
  await Promise.all([vs.data("puntaje", [{ p }]).runAsync(), vb.data("prob_proba", probs).runAsync()]);
}

async function proba() {
  [MOD_PIT, MOD_COMP] = await Promise.all([
    fetch("datos/modelo_parada.json").then((r) => r.json()),
    fetch("datos/modelo_compuesto.json").then((r) => r.json()),
  ]);
  prepararFormulario();
  const c = CFG.caso_inicial;
  cargarEnFormulario(c, c._desc, c._real);
}

// ------------------------------------------------------------------ inicio
// Se espera a la tipografía para que Vega mida bien los rótulos de los ejes.
await document.fonts.ready;
navegacion();
tallo();
explora().catch((e) => { console.error(e); $("#resumen-vista").textContent = "No se pudieron cargar los datos de exploración."; });
proba().catch((e) => { console.error(e); $("#r-veredicto").textContent = "No se pudo cargar el modelo."; });

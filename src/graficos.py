"""Gráficos de la aplicación, todos construidos con Altair.

Cada función devuelve un ``alt.Chart`` cuyo ``to_dict()`` se embebe en la página.
Los colores son los mismos en toda la aplicación:

* compuesto: SOFT rojo, MEDIUM ámbar, HARD pizarra (el blanco de Pirelli no se ve
  sobre fondo claro) y LLUVIA azul; siempre acompañados de su nombre;
* contexto de la parada: en seco y sin safety car (pizarra), con safety car (ámbar),
  a neumático de lluvia (azul);
* puntaje del modelo: un solo tono violeta, de claro a oscuro.

Los gráficos interactivos usan datos con nombre (``alt.NamedData``) que la página
carga y parámetros (``alt.param``) cuyo valor cambian los controles.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

ORDEN = ["SOFT", "MEDIUM", "HARD", "LLUVIA"]
COLOR_COMPUESTO = {"SOFT": "#d7263d", "MEDIUM": "#d99a00", "HARD": "#4f5d6b", "LLUVIA": "#2b83c6"}
CONTEXTOS = ["En seco, sin safety car", "Con safety car", "A neumático de lluvia"]
COLOR_CONTEXTO = {"En seco, sin safety car": "#4a5866", "Con safety car": "#d99a00", "A neumático de lluvia": "#2b83c6"}
VIOLETA = "#5b46c9"
VIOLETA_CLARO = "#d9d3f5"
GRIS_ALARMA_APAGADA = "#e7e5e0"
TINTA = "#1d1c1a"
TINTA_2 = "#55534e"
TINTA_3 = "#8a877f"
GRILLA = "#ebe8e1"
FUENTE = "Inter, system-ui, sans-serif"

ESCALA_COMPUESTO = alt.Scale(domain=ORDEN, range=[COLOR_COMPUESTO[c] for c in ORDEN])
ESCALA_CONTEXTO = alt.Scale(domain=CONTEXTOS, range=[COLOR_CONTEXTO[c] for c in CONTEXTOS])
ESCALA_PUNTAJE = alt.Scale(domain=[0, 1], range=["#efedfb", "#2e1f8f"])


def config(chart):
    return (chart
            .configure(font=FUENTE, background="transparent", padding={"left": 12, "right": 10, "top": 6, "bottom": 4})
            .configure_view(stroke=None)
            .configure_axis(labelColor=TINTA_2, titleColor=TINTA_2, labelFontSize=12, titleFontSize=12,
                            titleFontWeight=500, gridColor=GRILLA, domainColor="#cfcbc2", tickColor="#cfcbc2",
                            labelFont=FUENTE, titleFont=FUENTE)
            .configure_legend(labelColor=TINTA_2, titleColor=TINTA_2, labelFontSize=12, titleFontSize=12,
                              titleFontWeight=500, orient="top", symbolType="circle", labelFont=FUENTE,
                              titleFont=FUENTE)
            .configure_header(labelColor=TINTA_2, titleColor=TINTA_2, labelFontSize=12, labelFont=FUENTE)
            .configure_text(font=FUENTE, color=TINTA)
            # Ancho del contenedor; el alto lo fija cada gráfico. resize=True recalcula los márgenes
            # cuando la página carga o cambia los datos (rótulos de ejes incluidos).
            .properties(autosize=alt.AutoSizeParams(type="fit-x", contains="padding", resize=True)))


# --------------------------------------------------------------------------
# 1 · Los datos
# --------------------------------------------------------------------------
def grafico_datos(paradas_vuelta: pd.DataFrame, carreras: pd.DataFrame):
    """Cada fila, una carrera; cada círculo, una vuelta con paradas (área = pilotos que pararon)."""
    orden_y = list(carreras.sort_values("fecha").etiqueta)
    y = alt.Y("etiqueta:N", sort=orden_y, title=None,
              axis=alt.Axis(labelFontSize=10, labelLimit=150, ticks=False, domain=False, labelPadding=6))
    base = alt.Chart(carreras).mark_rule(color="#e3dfd6", strokeWidth=5, strokeCap="round").encode(
        x=alt.X("desde:Q", title="Vuelta de carrera", scale=alt.Scale(domain=[0, 80], nice=False),
                axis=alt.Axis(values=list(range(0, 81, 10)), grid=False)),
        x2="hasta:Q", y=y,
        tooltip=[alt.Tooltip("nombre:N", title="Carrera"), alt.Tooltip("temporada:O", title="Temporada"),
                 alt.Tooltip("vueltas_total:Q", title="Vueltas registradas", format=",d"),
                 alt.Tooltip("paradas:Q", title="Paradas", format=",d")])
    puntos = alt.Chart(paradas_vuelta).mark_circle(opacity=0.85, stroke="#fbfaf7", strokeWidth=1).encode(
        x="lap_number:Q", y=y,
        size=alt.Size("paradas:Q", title="Pilotos que paran",
                      scale=alt.Scale(domain=[1, 20], range=[14, 420]),
                      legend=alt.Legend(values=[1, 5, 10, 20], orient="bottom", symbolFillColor=TINTA_3,
                                        symbolStrokeWidth=0)),
        color=alt.Color("contexto:N", scale=ESCALA_CONTEXTO, title="Contexto",
                        legend=alt.Legend(orient="top", columns=1, title=None)),
        order=alt.Order("paradas:Q", sort="descending"),
        tooltip=[alt.Tooltip("nombre:N", title="Carrera"), alt.Tooltip("lap_number:Q", title="Vuelta"),
                 alt.Tooltip("paradas:Q", title="Pilotos que paran"), alt.Tooltip("contexto:N", title="Contexto")])
    return config((base + puntos).properties(width="container", height=alt.Step(13)))


# --------------------------------------------------------------------------
# 2 · Lo que encontramos
# --------------------------------------------------------------------------
def grafico_hallazgo(h4: pd.DataFrame):
    """Hipótesis 4 en seco: % de paradas que montan cada compuesto, con y sin safety car."""
    y = alt.Y("compuesto:N", sort=["SOFT", "MEDIUM", "HARD"], title=None,
              axis=alt.Axis(labelFontSize=13, labelFontWeight=600, ticks=False, domain=False, labelPadding=10))
    x = alt.X("pct:Q", title="% de las paradas en seco",
              scale=alt.Scale(domain=[0, 0.6]), axis=alt.Axis(format="%", values=[0, .1, .2, .3, .4, .5, .6]))
    ancho = h4.pivot(index="compuesto", columns="situacion", values="pct").reset_index()
    ancho.columns = ["compuesto", "con", "sin"]
    linea = alt.Chart(ancho).mark_rule(strokeWidth=3, color="#cfcbc2").encode(
        y=y, x=alt.X("sin:Q", scale=alt.Scale(domain=[0, 0.6])), x2="con:Q")
    puntos = alt.Chart(h4).mark_point(filled=True, size=260, opacity=1, stroke="#fbfaf7", strokeWidth=2).encode(
        y=y, x=x,
        shape=alt.Shape("situacion:N", scale=alt.Scale(domain=["Sin safety car", "Con safety car"],
                                                       range=["circle", "diamond"]), title=None),
        color=alt.Color("situacion:N", scale=alt.Scale(domain=["Sin safety car", "Con safety car"],
                                                       range=[COLOR_CONTEXTO["En seco, sin safety car"],
                                                              COLOR_CONTEXTO["Con safety car"]]), title=None),
        tooltip=[alt.Tooltip("situacion:N", title="Situación"), alt.Tooltip("compuesto:N", title="Compuesto"),
                 alt.Tooltip("pct:Q", title="% de paradas", format=".1%"),
                 alt.Tooltip("paradas:Q", title="Paradas en seco del grupo", format=",d")])
    etiquetas = alt.Chart(h4).mark_text(dy=-17, fontSize=12, fontWeight=600, color=TINTA).encode(
        y=y, x=x, text=alt.Text("pct:Q", format=".0%"))
    return config((linea + puntos + etiquetas).properties(width="container", height=210))


def grafico_h1(hist: pd.DataFrame):
    """Hipótesis 1 corregida: histograma de la edad del neumático al empezar la vuelta, normalizado por grupo."""
    return config(alt.Chart(hist).mark_line(interpolate="step-after", strokeWidth=2.5).encode(
        x=alt.X("desde:Q", title="Edad del neumático al empezar la vuelta", scale=alt.Scale(domain=[0, 60])),
        y=alt.Y("pct:Q", title="% de las vueltas del grupo"),
        color=alt.Color("grupo:N", title=None, scale=alt.Scale(domain=["Sigue en pista", "Entra a boxes"],
                                                               range=["#a3a097", VIOLETA])),
        tooltip=[alt.Tooltip("grupo:N", title="Grupo"), alt.Tooltip("desde:Q", title="Desde (vueltas)"),
                 alt.Tooltip("hasta:Q", title="Hasta (vueltas)"), alt.Tooltip("pct:Q", title="% del grupo", format=".1f")]
    ).properties(width="container", height=220))


# --------------------------------------------------------------------------
# 3 · El modelo
# --------------------------------------------------------------------------
def grafico_modelo(por_contexto: pd.DataFrame):
    """% de paradas reales de 2025 con alarma en esa vuelta, según el contexto de la parada."""
    y = alt.Y("contexto:N", sort=CONTEXTOS, title=None,
              axis=alt.Axis(labelFontSize=13, labelFontWeight=600, ticks=False, domain=False, labelPadding=10,
                            labelLimit=220))
    barras = alt.Chart(por_contexto).mark_bar(cornerRadiusEnd=4, height=26).encode(
        y=y,
        x=alt.X("pct:Q", title="% con alarma en esa vuelta",
                scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", values=[0, .25, .5, .75, 1])),
        color=alt.Color("contexto:N", scale=ESCALA_CONTEXTO, legend=None),
        tooltip=[alt.Tooltip("contexto:N", title="Parada"), alt.Tooltip("paradas:Q", title="Paradas reales"),
                 alt.Tooltip("anticipadas:Q", title="Con alarma"), alt.Tooltip("pct:Q", title="%", format=".1%")])
    # Rótulo afuera de la barra si es corta; adentro, en blanco, si es larga (no se sale del gráfico).
    fuera = alt.Chart(por_contexto).transform_filter("datum.pct < 0.45").mark_text(
        align="left", dx=8, fontSize=13, fontWeight=600, color=TINTA).encode(y=y, x="pct:Q", text="rotulo:N")
    dentro = alt.Chart(por_contexto).transform_filter("datum.pct >= 0.45").mark_text(
        align="right", dx=-10, fontSize=13, fontWeight=600, color="white").encode(y=y, x="pct:Q", text="rotulo:N")
    return config((barras + fuera + dentro).properties(width="container", height=170))


def grafico_matriz(matriz: pd.DataFrame):
    """Matriz de confusión del compuesto (test 2025): conteos y % por fila (recall)."""
    base = alt.Chart(matriz).encode(
        x=alt.X("predicho:N", sort=ORDEN, title="Compuesto que predice el modelo", axis=alt.Axis(labelAngle=0, orient="top")),
        y=alt.Y("real:N", sort=ORDEN, title="Compuesto que se montó"))
    celdas = base.mark_rect(stroke="#fbfaf7", strokeWidth=2, cornerRadius=3).encode(
        color=alt.Color("pct_fila:Q", scale=alt.Scale(domain=[0, 1], range=["#f4f2fb", "#3a2aa6"]), legend=None),
        tooltip=[alt.Tooltip("real:N", title="Real"), alt.Tooltip("predicho:N", title="Predicho"),
                 alt.Tooltip("n:Q", title="Paradas"), alt.Tooltip("pct_fila:Q", title="% de la fila", format=".1%")])
    texto = base.mark_text(fontSize=12, fontWeight=600).encode(
        text="rotulo:N", color=alt.condition("datum.pct_fila > 0.45", alt.value("white"), alt.value(TINTA)))
    return config((celdas + texto).properties(width="container", height=210))


def grafico_familias(tabla: pd.DataFrame, titulo_x: str):
    """Media ± desvío del F1 de validación por carrera de cada familia (4 pedazos)."""
    orden = list(tabla.sort_values("f1_validacion", ascending=False).modelo)
    y = alt.Y("modelo:N", sort=orden, title=None, axis=alt.Axis(labelLimit=220, ticks=False, domain=False))
    tope = float((tabla.f1_validacion + tabla.desvio).max()) * 1.1
    escala = alt.Scale(domain=[0, tope], nice=False)
    barra = alt.Chart(tabla).mark_rule(strokeWidth=2, color=TINTA_3).encode(y=y, x=alt.X("lo:Q", scale=escala), x2="hi:Q")
    punto = alt.Chart(tabla).mark_circle(size=110, opacity=1).encode(
        y=y, x=alt.X("f1_validacion:Q", title=titulo_x, scale=escala),
        color=alt.condition("datum.elegido", alt.value(VIOLETA), alt.value("#8a877f")),
        tooltip=[alt.Tooltip("modelo:N", title="Modelo"), alt.Tooltip("f1_validacion:Q", title="Media", format=".3f"),
                 alt.Tooltip("desvio:Q", title="Desvío", format=".3f"),
                 alt.Tooltip("f1_entrenamiento:Q", title="F1 en entrenamiento", format=".3f")])
    return config((barra + punto).transform_calculate(
        lo="datum.f1_validacion - datum.desvio", hi="datum.f1_validacion + datum.desvio"
    ).properties(width="container", height=alt.Step(30)))


def grafico_umbral(tabla: pd.DataFrame, umbral: float):
    """Precisión, recall y F1 de la clase 'para' según el umbral (fuera de fold, 2023-2024)."""
    largo = tabla.melt(id_vars="umbral", value_vars=["precision", "recall", "f1"], var_name="metrica", value_name="valor")
    largo["metrica"] = largo.metrica.map({"precision": "Precisión", "recall": "Recall", "f1": "F1"})
    lineas = alt.Chart(largo).mark_line(strokeWidth=2).encode(
        x=alt.X("umbral:Q", title="Umbral sobre el puntaje de parada", scale=alt.Scale(domain=[0.1, 0.9])),
        y=alt.Y("valor:Q", title=None, axis=alt.Axis(format="%")),
        color=alt.Color("metrica:N", title=None, scale=alt.Scale(domain=["Recall", "Precisión", "F1"],
                                                                 range=["#2b83c6", "#d99a00", VIOLETA])),
        tooltip=[alt.Tooltip("metrica:N", title="Métrica"), alt.Tooltip("umbral:Q", title="Umbral", format=".3f"),
                 alt.Tooltip("valor:Q", title="Valor", format=".1%")])
    regla = alt.Chart(pd.DataFrame({"u": [umbral]})).mark_rule(strokeDash=[4, 3], color=TINTA).encode(x="u:Q")
    texto = alt.Chart(pd.DataFrame({"u": [umbral], "t": [f"elegido: {umbral:.3f}".replace(".", ",")]})).mark_text(
        align="left", dx=6, y=8, fontSize=11, color=TINTA).encode(x="u:Q", text="t:N")
    return config((lineas + regla + texto).properties(width="container", height=220))


def grafico_importancia(tabla: pd.DataFrame, titulo_x: str):
    orden = list(tabla.sort_values("caida", ascending=False).variable)
    y = alt.Y("variable:N", sort=orden, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=200))
    barras = alt.Chart(tabla).mark_bar(height=12, cornerRadiusEnd=3).encode(
        y=y, x=alt.X("caida:Q", title=titulo_x),
        color=alt.condition("datum.caida > 0", alt.value(VIOLETA), alt.value("#c9c5bb")),
        tooltip=[alt.Tooltip("variable:N", title="Variable"), alt.Tooltip("caida:Q", title="Caída media", format=".4f"),
                 alt.Tooltip("desvio:Q", title="Desvío", format=".4f"),
                 alt.Tooltip("folds_positivos:Q", title="Pedazos con caída > 0")])
    error = alt.Chart(tabla).mark_rule(color=TINTA_3).encode(y=y, x="lo:Q", x2="hi:Q")
    return config((barras + error).transform_calculate(lo="datum.caida - datum.desvio", hi="datum.caida + datum.desvio")
                  .properties(width="container", height=alt.Step(18)))


# --------------------------------------------------------------------------
# 4 · Explorá (datos con nombre que carga la página; parámetros que cambian los controles)
# --------------------------------------------------------------------------
def _p_umbral(valor):
    return alt.param(name="umbral", value=valor)


def grafico_panorama(umbral: float):
    """Cada carrera, sus paradas reales: con alarma en la vuelta (violeta) o sin alarma (gris)."""
    p_u = _p_umbral(umbral)
    p_temp = alt.param(name="temporada", value=2025)
    p_ctx = alt.param(name="contexto", value="Todas")
    y = alt.Y("carrera:N", sort=alt.EncodingSortField("orden", op="min"), title=None,
              axis=alt.Axis(ticks=False, domain=False, labelLimit=170, labelFontSize=11))
    base = (alt.Chart(alt.NamedData("paradas"))
            .transform_filter("temporada == 0 || datum.temporada == temporada")
            .transform_filter("contexto == 'Todas' || datum.contexto == contexto")
            .transform_calculate(resultado="datum.puntaje >= umbral ? 'Con alarma' : 'Sin alarma'"))
    barras = base.mark_bar(height=11, stroke="#fbfaf7", strokeWidth=1).encode(
        y=y,
        x=alt.X("count():Q", title="Paradas reales", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("resultado:N", title=None,
                        scale=alt.Scale(domain=["Con alarma", "Sin alarma"], range=[VIOLETA, "#cdc9bf"])),
        order=alt.Order("resultado:N", sort="ascending"),
        tooltip=[alt.Tooltip("carrera:N", title="Carrera"), alt.Tooltip("resultado:N", title="Resultado"),
                 alt.Tooltip("count():Q", title="Paradas")])
    return config(barras.add_params(p_u, p_temp, p_ctx).properties(width="container", height=alt.Step(15)))


def grafico_carrera(umbral: float):
    """Mapa de la carrera: piloto × vuelta; violeta = alarma encendida; círculos = paradas reales."""
    p_u = _p_umbral(umbral)
    p_pil = alt.param(name="piloto", value="")
    p_sel = alt.param(name="seleccion", value="")
    y = alt.Y("piloto:N", sort=alt.EncodingSortField("orden_piloto", op="min"), title=None,
              axis=alt.Axis(ticks=False, domain=False, labelFontSize=11, labelPadding=6))
    x = alt.X("vuelta:O", title="Vuelta", axis=alt.Axis(labelAngle=0, labelExpr="datum.value % 5 == 0 ? datum.value : ''",
                                                         ticks=False, domain=False, labelFontSize=10))
    base = alt.Chart(alt.NamedData("carrera"))
    celdas = base.mark_rect(cornerRadius=1.5, stroke="#fbfaf7", strokeWidth=0.6).encode(
        x=x, y=y,
        color=alt.condition("datum.puntaje >= umbral",
                            alt.Color("puntaje:Q", scale=alt.Scale(domain=[0.3, 1], range=["#a99cf0", "#21137a"]),
                                      title="Puntaje", legend=alt.Legend(format=".1f", gradientLength=110)),
                            alt.value(GRIS_ALARMA_APAGADA)),
        opacity=alt.condition("piloto == '' || datum.piloto == piloto", alt.value(1), alt.value(0.25)),
        tooltip=[alt.Tooltip("nombre:N", title="Piloto"), alt.Tooltip("vuelta:O", title="Vuelta"),
                 alt.Tooltip("puntaje:Q", title="Puntaje de parada", format=".3f"),
                 alt.Tooltip("alarma:N", title="Alarma"), alt.Tooltip("real:N", title="¿Paró?"),
                 alt.Tooltip("comp_pred:N", title="Compuesto que propone"),
                 alt.Tooltip("compound_prev:N", title="Neumático en la vuelta anterior"),
                 alt.Tooltip("tyre_age_prev:Q", title="Edad del neumático")]
    ).transform_calculate(
        alarma="datum.puntaje >= umbral ? 'sí' : 'no'",
        real="datum.para ? 'sí, monta ' + datum.objetivo : 'no'")
    paradas = base.transform_filter("datum.para").mark_point(
        filled=True, size=55, shape="circle", stroke="white", strokeWidth=1.2, opacity=1).encode(
        x=x, y=y,
        color=alt.Color("objetivo:N", scale=ESCALA_COMPUESTO, title="Parada real",
                        legend=alt.Legend(symbolStrokeColor="white", orient="bottom", columns=4)),
        tooltip=[alt.Tooltip("nombre:N", title="Piloto"), alt.Tooltip("vuelta:O", title="Vuelta"),
                 alt.Tooltip("objetivo:N", title="Paró y montó"),
                 alt.Tooltip("puntaje:Q", title="Puntaje de parada", format=".3f"),
                 alt.Tooltip("comp_pred:N", title="Compuesto que propone")])
    marco = base.transform_filter("datum.id == seleccion").mark_rect(fill=None, stroke=TINTA, strokeWidth=2).encode(x=x, y=y)
    return config((celdas + paradas + marco).add_params(p_u, p_pil, p_sel).resolve_scale(color="independent")
                  .properties(width="container", height=alt.Step(17)))


def grafico_trayectoria(umbral: float):
    """Puntaje de parada del piloto elegido vuelta a vuelta, con el umbral y sus paradas reales."""
    p_u = _p_umbral(umbral)
    base = alt.Chart(alt.NamedData("trayectoria"))
    x = alt.X("vuelta:Q", title="Vuelta", axis=alt.Axis(tickMinStep=5))
    sc = base.transform_filter("datum.sc").transform_calculate(
        a="datum.vuelta - 0.5", b="datum.vuelta + 0.5").mark_rect(color="#f6e3b0", opacity=0.8).encode(
        x="a:Q", x2="b:Q", y=alt.value(0), y2=alt.value(180),
        tooltip=[alt.Tooltip("vuelta:Q", title="Vuelta con safety car")])
    linea = base.mark_line(color=VIOLETA, strokeWidth=2).encode(
        x=x, y=alt.Y("puntaje:Q", title="Puntaje de parada", scale=alt.Scale(domain=[0, 1])))
    regla =base.mark_rule(strokeDash=[5, 4], color=TINTA_2, strokeWidth=1.2).encode(y="u:Q").transform_aggregate(
        n="count()").transform_calculate(u="umbral")
    paradas = base.transform_filter("datum.para").mark_point(filled=True, size=120, stroke="white", strokeWidth=1.5,
                                                              opacity=1).encode(
        x=x, y="puntaje:Q", color=alt.Color("objetivo:N", scale=ESCALA_COMPUESTO, title="Parada real"),
        tooltip=[alt.Tooltip("vuelta:Q", title="Vuelta"), alt.Tooltip("objetivo:N", title="Montó"),
                 alt.Tooltip("puntaje:Q", title="Puntaje", format=".3f")])
    puntos = base.mark_circle(size=60, opacity=0).encode(
        x=x, y="puntaje:Q",
        tooltip=[alt.Tooltip("vuelta:Q", title="Vuelta"), alt.Tooltip("puntaje:Q", title="Puntaje", format=".3f"),
                 alt.Tooltip("compound_prev:N", title="Neumático"), alt.Tooltip("tyre_age_prev:Q", title="Edad")])
    return config((sc + linea + regla + paradas + puntos).add_params(p_u).properties(width="container", height=180))


def grafico_probabilidades(nombre_datos: str):
    """Probabilidad de cada compuesto según el modelo de compuesto."""
    y = alt.Y("compuesto:N", sort=ORDEN, title=None, axis=alt.Axis(ticks=False, domain=False, labelFontWeight=600))
    barras = alt.Chart(alt.NamedData(nombre_datos)).mark_bar(height=14, cornerRadiusEnd=3).encode(
        y=y, x=alt.X("p:Q", title=None, scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", values=[0, .5, 1])),
        color=alt.Color("compuesto:N", scale=ESCALA_COMPUESTO, legend=None),
        tooltip=[alt.Tooltip("compuesto:N", title="Compuesto"), alt.Tooltip("p:Q", title="Probabilidad", format=".1%")])
    texto = alt.Chart(alt.NamedData(nombre_datos)).mark_text(align="left", dx=6, fontSize=12, fontWeight=600,
                                                             color=TINTA).encode(
        y=y, x="p:Q", text=alt.Text("p:Q", format=".0%"))
    return config((barras + texto).properties(width="container", height=130))


def grafico_puntaje(umbral: float):
    """Puntaje de parada del caso ingresado contra el umbral (barra de 0 a 1)."""
    p_u = _p_umbral(umbral)
    base = alt.Chart(alt.NamedData("puntaje"))
    fondo = base.mark_bar(color="#efece6", height=22, cornerRadius=4).encode(
        x=alt.X("uno:Q", scale=alt.Scale(domain=[0, 1]), title=None, axis=alt.Axis(format=".2f", values=[0, .25, .5, .75, 1])),
    ).transform_calculate(uno="1")
    barra = base.mark_bar(height=22, cornerRadius=4).encode(
        x="p:Q", color=alt.condition("datum.p >= umbral", alt.value(VIOLETA), alt.value("#a3a097")),
        tooltip=[alt.Tooltip("p:Q", title="Puntaje de parada", format=".3f")])
    regla = base.mark_rule(color=TINTA, strokeWidth=2, strokeDash=[3, 2]).encode(x="u:Q").transform_calculate(u="umbral")
    texto = base.mark_text(dy=-22, dx=6, fontSize=11, color=TINTA, align="left").encode(
        x="u:Q", text="t:N").transform_calculate(u="umbral", t="'umbral ' + format(umbral, '.3f')")
    return config((fondo + barra + regla + texto).add_params(p_u).properties(width="container", height=60))


# --------------------------------------------------------------------------
# Correcciones de la Entrega 3
# --------------------------------------------------------------------------
def grafico_pr(tabla: pd.DataFrame, umbral: float, prevalencia: float):
    """Curva precisión–recall fuera de pedazo (2023-2024): recall en X, precisión en Y, umbrales rotulados."""
    t = tabla[tabla.alarmas > 0].copy()  # sin alarmas la precisión no está definida
    t["rotulo"] = t.umbral.map(lambda u: f"{u:.3f}".rstrip("0").rstrip(",").replace(".", ","))
    marcados = t[t.umbral.round(3).isin([0.1, 0.2, 0.3, 0.4, round(umbral, 3), 0.55, 0.7])].copy()
    marcados["elegido"] = marcados.umbral.round(3).eq(round(umbral, 3))
    x = alt.X("recall:Q", title="Recall (paradas reales con alarma)", scale=alt.Scale(domain=[0, 1]),
              axis=alt.Axis(format="%"))
    y = alt.Y("precision:Q", title="Precisión (alarmas que son parada)", scale=alt.Scale(domain=[0, float(t.precision.max()) * 1.08], nice=False),
              axis=alt.Axis(format="%"))
    linea = alt.Chart(t).mark_line(color="#a3a097", strokeWidth=2).encode(x=x, y=y, order="umbral:Q")
    puntos = alt.Chart(marcados).mark_circle(size=90, opacity=1).encode(
        x=x, y=y, color=alt.condition("datum.elegido", alt.value(VIOLETA), alt.value(TINTA_2)),
        tooltip=[alt.Tooltip("umbral:Q", title="Umbral", format=".3f"), alt.Tooltip("recall:Q", title="Recall", format=".1%"),
                 alt.Tooltip("precision:Q", title="Precisión", format=".1%"), alt.Tooltip("alarmas:Q", title="Alarmas", format=",d")])
    texto = alt.Chart(marcados).mark_text(dy=-12, fontSize=11, fontWeight=600, color=TINTA).encode(
        x=x, y=y, text="rotulo:N")
    piso = alt.Chart(pd.DataFrame({"p": [prevalencia]})).mark_rule(color="#a3a097", strokeDash=[4, 3]).encode(y="p:Q")
    piso_t = alt.Chart(pd.DataFrame({"p": [prevalencia], "x": [0.6], "t": ["piso: siempre parar"]})).mark_text(
        align="left", dy=-7, fontSize=11, color=TINTA_2).encode(x="x:Q", y="p:Q", text="t:N")
    return config((piso + piso_t + linea + puntos + texto).properties(width="container", height=240))


def grafico_distancias(dist: pd.DataFrame):
    """Falsas alarmas de 2025 según cuántas vueltas faltaban para la próxima parada real del piloto."""
    orden = list(dist.categoria)
    y = alt.Y("categoria:N", sort=orden, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=200))
    barras = alt.Chart(dist).mark_bar(height=18, cornerRadiusEnd=3).encode(
        y=y, x=alt.X("fp:Q", title="Vueltas con falsa alarma (2025)"),
        color=alt.condition("datum.cercana", alt.value(VIOLETA), alt.value("#a3a097")),
        tooltip=[alt.Tooltip("categoria:N", title="Próxima parada"), alt.Tooltip("fp:Q", title="Falsas alarmas", format=",d"),
                 alt.Tooltip("pct:Q", title="%", format=".1%")])
    texto = alt.Chart(dist).mark_text(align="left", dx=6, fontSize=12, color=TINTA).encode(
        y=y, x="fp:Q", text="rotulo:N")
    return config((barras + texto).properties(width="container", height=alt.Step(30)))


def grafico_mdi(tabla: pd.DataFrame, titulo_x: str):
    """Importancia del bosque sin permutación (disminución media de impureza), por variable original."""
    orden = list(tabla.sort_values("importancia", ascending=False).variable)
    return config(alt.Chart(tabla).mark_bar(height=12, cornerRadiusEnd=3, color="#6f7d8a").encode(
        y=alt.Y("variable:N", sort=orden, title=None, axis=alt.Axis(ticks=False, domain=False, labelLimit=200)),
        x=alt.X("importancia:Q", title=titulo_x, axis=alt.Axis(format="%")),
        tooltip=[alt.Tooltip("variable:N", title="Variable"), alt.Tooltip("importancia:Q", title="Importancia", format=".1%")]
    ).properties(width="container", height=alt.Step(18)))

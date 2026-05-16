
# Calculadora de Costos de Producción Agrícola — v4
# Novedades sobre v3:
# - Guardar / cargar escenarios (JSON descargable + upload)
# - Gráfica de distribución de costos (pie + barras)
# - Comparar escenarios guardados en sesión

import json
import io
import datetime as dt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import cm
from reportlab.lib import colors

st.set_page_config(page_title="Calculadora de Costos Agrícolas v4", layout="wide")

# ---------- Utilidades ----------
def money(x, cur):
    try:
        return f"{cur} {x:,.2f}"
    except Exception:
        return f"{cur} {x}"

def empty_table_per_ha():
    return pd.DataFrame({"Concepto": [""]*3, "Costo por ha": [0.0]*3, "Notas": [""]*3})

def empty_table_totales():
    return pd.DataFrame({"Concepto": [""]*3, "Costo total (temporada)": [0.0]*3, "Notas": [""]*3})

def sanitize_per_ha(df):
    cols = ["Concepto", "Costo por ha", "Notas"]
    for c in cols:
        if c not in df.columns:
            df[c] = "" if c != "Costo por ha" else 0.0
    df["Costo por ha"] = pd.to_numeric(df["Costo por ha"], errors="coerce").fillna(0.0)
    df["Concepto"] = df["Concepto"].astype(str)
    df["Notas"] = df["Notas"].astype(str)
    return df[cols]

def sanitize_totales(df):
    cols = ["Concepto", "Costo total (temporada)", "Notas"]
    for c in cols:
        if c not in df.columns:
            df[c] = "" if c != "Costo total (temporada)" else 0.0
    df["Costo total (temporada)"] = pd.to_numeric(df["Costo total (temporada)"], errors="coerce").fillna(0.0)
    df["Concepto"] = df["Concepto"].astype(str)
    df["Notas"] = df["Notas"].astype(str)
    return df[cols]

def df_to_records(df):
    return df.to_dict(orient="records")

def records_to_df(records, modo):
    df = pd.DataFrame(records)
    return sanitize_per_ha(df) if modo == "Por hectárea" else sanitize_totales(df)

# ---------- Estado ----------
for key, default in [
    ("modo", "Por hectárea"),
    ("insumos", empty_table_per_ha()),
    ("mano_obra", empty_table_per_ha()),
    ("otros", empty_table_per_ha()),
    ("escenarios", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- Encabezado ----------
st.title("Calculadora de Costos de Producción Agrícola — v4")
st.caption("Costos por ha o totales · Gráficas · Guardar/cargar escenarios · Comparar temporadas · PDF")

c0, c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1, 1])
with c0:
    st.session_state.modo = st.radio("Modo de captura", ["Por hectárea", "Totales de temporada"], horizontal=True)
with c1:
    nombre_escenario = st.text_input("Nombre del escenario", value="Temporada_" + dt.date.today().isoformat())
with c2:
    moneda = st.selectbox("Moneda", ["MXN", "USD", "EUR"], index=0)
with c3:
    hectareas = st.number_input("Hectáreas", min_value=0.1, value=10.0, step=1.0)
with c4:
    cultivo = st.text_input("Cultivo (opcional)", value="")

st.markdown("---")

# ---------- Tablas de costos ----------
st.subheader("Costos — según modo de captura")
tab1, tab2, tab3 = st.tabs(["Insumos", "Mano de obra", "Otros gastos"])

if st.session_state.modo == "Por hectárea":
    with tab1:
        st.info("Ingresa costos por ha: fertilizantes, correctores, pesticidas, etc.")
        t1 = st.data_editor(
            st.session_state.insumos if "Costo por ha" in st.session_state.insumos.columns else empty_table_per_ha(),
            num_rows="dynamic", use_container_width=True, key="tbl_insumos_ha")
        st.session_state.insumos = sanitize_per_ha(t1)
    with tab2:
        st.info("Cuadrillas, maquinaria, supervisión, etc.")
        t2 = st.data_editor(
            st.session_state.mano_obra if "Costo por ha" in st.session_state.mano_obra.columns else empty_table_per_ha(),
            num_rows="dynamic", use_container_width=True, key="tbl_mano_ha")
        st.session_state.mano_obra = sanitize_per_ha(t2)
    with tab3:
        st.info("Energía, agua, arrendamientos, transporte, seguros, otros.")
        t3 = st.data_editor(
            st.session_state.otros if "Costo por ha" in st.session_state.otros.columns else empty_table_per_ha(),
            num_rows="dynamic", use_container_width=True, key="tbl_otros_ha")
        st.session_state.otros = sanitize_per_ha(t3)
else:
    with tab1:
        st.info("Ingresa costos totales de la temporada. Calculamos por ha automáticamente.")
        t1 = st.data_editor(
            st.session_state.insumos if "Costo total (temporada)" in st.session_state.insumos.columns else empty_table_totales(),
            num_rows="dynamic", use_container_width=True, key="tbl_insumos_tot")
        st.session_state.insumos = sanitize_totales(t1)
    with tab2:
        st.info("Cuadrillas, maquinaria, supervisión, etc.")
        t2 = st.data_editor(
            st.session_state.mano_obra if "Costo total (temporada)" in st.session_state.mano_obra.columns else empty_table_totales(),
            num_rows="dynamic", use_container_width=True, key="tbl_mano_tot")
        st.session_state.mano_obra = sanitize_totales(t2)
    with tab3:
        st.info("Energía, agua, arrendamientos, transporte, seguros, otros.")
        t3 = st.data_editor(
            st.session_state.otros if "Costo total (temporada)" in st.session_state.otros.columns else empty_table_totales(),
            num_rows="dynamic", use_container_width=True, key="tbl_otros_tot")
        st.session_state.otros = sanitize_totales(t3)

# ---------- Cálculo de totales ----------
if st.session_state.modo == "Por hectárea":
    insumos_ha = st.session_state.insumos["Costo por ha"].sum() if "Costo por ha" in st.session_state.insumos.columns else 0.0
    mano_ha    = st.session_state.mano_obra["Costo por ha"].sum() if "Costo por ha" in st.session_state.mano_obra.columns else 0.0
    otros_ha   = st.session_state.otros["Costo por ha"].sum() if "Costo por ha" in st.session_state.otros.columns else 0.0
    total_insumos_temp = insumos_ha * hectareas
    total_mano_temp    = mano_ha * hectareas
    total_otros_temp   = otros_ha * hectareas
else:
    total_insumos_temp = st.session_state.insumos["Costo total (temporada)"].sum() if "Costo total (temporada)" in st.session_state.insumos.columns else 0.0
    total_mano_temp    = st.session_state.mano_obra["Costo total (temporada)"].sum() if "Costo total (temporada)" in st.session_state.mano_obra.columns else 0.0
    total_otros_temp   = st.session_state.otros["Costo total (temporada)"].sum() if "Costo total (temporada)" in st.session_state.otros.columns else 0.0
    insumos_ha = total_insumos_temp / hectareas if hectareas > 0 else 0.0
    mano_ha    = total_mano_temp / hectareas if hectareas > 0 else 0.0
    otros_ha   = total_otros_temp / hectareas if hectareas > 0 else 0.0

total_ha       = insumos_ha + mano_ha + otros_ha
total_temporada = total_insumos_temp + total_mano_temp + total_otros_temp

# ---------- Resultados ----------
st.markdown("---")
st.subheader("Resultados")
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Insumos (por ha)", money(insumos_ha, moneda))
with k2:
    st.metric("Mano de obra (por ha)", money(mano_ha, moneda))
with k3:
    st.metric("Otros (por ha)", money(otros_ha, moneda))
with k4:
    st.metric("Total (por ha)", money(total_ha, moneda))

st.markdown("### Total por temporada")
st.success(f"{money(total_temporada, moneda)}  \n_(Equivale a total por ha × {hectareas} ha)_")

# ---------- Costo por kilo ----------
st.markdown("---")
st.subheader("Costo de producción por kilo")
cc1, cc2, cc3 = st.columns(3)
with cc1:
    produccion_total_kg = st.number_input("Producción total (kg)", min_value=0.0, value=0.0, step=1000.0)
with cc2:
    precio_venta_kg = st.number_input(f"Precio de venta por kg ({moneda})", min_value=0.0, value=0.0, step=1.0)
with cc3:
    rendimiento_calc = (produccion_total_kg / hectareas) if hectareas > 0 else 0.0
    st.metric("Rendimiento (kg/ha)", f"{rendimiento_calc:,.2f}")

costo_por_kg  = (total_temporada / produccion_total_kg) if produccion_total_kg > 0 else 0.0
ingreso_total = produccion_total_kg * precio_venta_kg
margen_total  = ingreso_total - total_temporada
margen_por_kg = (margen_total / produccion_total_kg) if produccion_total_kg > 0 else 0.0

cm1, cm2, cm3, cm4 = st.columns(4)
with cm1:
    st.metric("Costo por kg", money(costo_por_kg, moneda))
with cm2:
    st.metric("Ingreso total", money(ingreso_total, moneda))
with cm3:
    st.metric("Margen total", money(margen_total, moneda))
with cm4:
    st.metric("Margen por kg", money(margen_por_kg, moneda))

# ========== NUEVO: GRÁFICAS ==========
st.markdown("---")
st.subheader("Distribución de costos")

categorias   = ["Insumos", "Mano de obra", "Otros"]
valores_temp = [total_insumos_temp, total_mano_temp, total_otros_temp]
valores_ha   = [insumos_ha, mano_ha, otros_ha]

if total_temporada > 0:
    g1, g2 = st.columns(2)
    with g1:
        fig_pie = px.pie(
            names=categorias,
            values=valores_temp,
            title=f"Distribución de costos (temporada, {moneda})",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_pie.update_traces(textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)
    with g2:
        fig_bar = px.bar(
            x=categorias,
            y=valores_temp,
            labels={"x": "Categoría", "y": f"Costo ({moneda})"},
            title=f"Costos por categoría (temporada, {moneda})",
            color=categorias,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_bar.update_layout(showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("Ingresa costos para ver las gráficas.")

# ========== NUEVO: GUARDAR / CARGAR ESCENARIOS ==========
st.markdown("---")
st.subheader("Guardar y cargar escenarios")

def escenario_actual():
    return {
        "nombre": nombre_escenario,
        "cultivo": cultivo,
        "moneda": moneda,
        "hectareas": hectareas,
        "modo": st.session_state.modo,
        "produccion_total_kg": produccion_total_kg,
        "precio_venta_kg": precio_venta_kg,
        "insumos": df_to_records(st.session_state.insumos),
        "mano_obra": df_to_records(st.session_state.mano_obra),
        "otros": df_to_records(st.session_state.otros),
        # KPIs calculados (solo para referencia en comparación)
        "total_ha": total_ha,
        "total_temporada": total_temporada,
        "costo_por_kg": costo_por_kg,
        "margen_total": margen_total,
    }

sg1, sg2 = st.columns(2)
with sg1:
    st.markdown("**Guardar escenario actual**")
    if st.button("Guardar en sesión"):
        st.session_state.escenarios[nombre_escenario] = escenario_actual()
        st.success(f"Escenario '{nombre_escenario}' guardado.")

    if st.session_state.escenarios:
        json_bytes = json.dumps(st.session_state.escenarios, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "⬇️ Descargar todos los escenarios (JSON)",
            data=json_bytes,
            file_name="escenarios_costos.json",
            mime="application/json",
        )

with sg2:
    st.markdown("**Cargar escenarios desde archivo JSON**")
    uploaded = st.file_uploader("Sube un archivo de escenarios (.json)", type="json", key="upload_json")
    if uploaded:
        try:
            cargados = json.loads(uploaded.read().decode("utf-8"))
            st.session_state.escenarios.update(cargados)
            st.success(f"Se cargaron {len(cargados)} escenario(s).")
        except Exception as e:
            st.error(f"Error al leer el archivo: {e}")

    if st.session_state.escenarios:
        sel = st.selectbox("Cargar escenario a la pantalla", ["— selecciona —"] + list(st.session_state.escenarios.keys()))
        if sel != "— selecciona —" and st.button("Cargar escenario seleccionado"):
            esc = st.session_state.escenarios[sel]
            st.session_state.modo     = esc["modo"]
            st.session_state.insumos  = records_to_df(esc["insumos"], esc["modo"])
            st.session_state.mano_obra = records_to_df(esc["mano_obra"], esc["modo"])
            st.session_state.otros    = records_to_df(esc["otros"], esc["modo"])
            st.success(f"Escenario '{sel}' cargado. Recarga la página si los números no actualizan.")
            st.rerun()

# ========== NUEVO: COMPARAR ESCENARIOS ==========
if len(st.session_state.escenarios) >= 2:
    st.markdown("---")
    st.subheader("Comparar escenarios")

    nombres = list(st.session_state.escenarios.keys())
    col_a, col_b = st.columns(2)
    with col_a:
        esc_a = st.selectbox("Escenario A", nombres, key="cmp_a")
    with col_b:
        esc_b = st.selectbox("Escenario B", nombres, index=min(1, len(nombres)-1), key="cmp_b")

    if esc_a != esc_b:
        a = st.session_state.escenarios[esc_a]
        b = st.session_state.escenarios[esc_b]

        # Tabla comparativa
        filas = [
            ("Cultivo",          a.get("cultivo","-"), b.get("cultivo","-")),
            ("Hectáreas",        f"{a['hectareas']}", f"{b['hectareas']}"),
            ("Moneda",           a["moneda"], b["moneda"]),
            ("Total por ha",     money(a["total_ha"], a["moneda"]), money(b["total_ha"], b["moneda"])),
            ("Total temporada",  money(a["total_temporada"], a["moneda"]), money(b["total_temporada"], b["moneda"])),
            ("Costo por kg",     money(a["costo_por_kg"], a["moneda"]), money(b["costo_por_kg"], b["moneda"])),
            ("Margen total",     money(a["margen_total"], a["moneda"]), money(b["margen_total"], b["moneda"])),
        ]
        df_cmp = pd.DataFrame(filas, columns=["Indicador", esc_a, esc_b])
        st.dataframe(df_cmp, use_container_width=True, hide_index=True)

        # Gráfica de barras comparativa
        kpis     = ["Total temporada", "Margen total"]
        vals_a   = [a["total_temporada"], a["margen_total"]]
        vals_b   = [b["total_temporada"], b["margen_total"]]
        fig_cmp  = go.Figure(data=[
            go.Bar(name=esc_a, x=kpis, y=vals_a, marker_color="#4CAF50"),
            go.Bar(name=esc_b, x=kpis, y=vals_b, marker_color="#2196F3"),
        ])
        fig_cmp.update_layout(barmode="group", title="Comparación de KPIs principales")
        st.plotly_chart(fig_cmp, use_container_width=True)
    else:
        st.info("Selecciona dos escenarios diferentes para comparar.")

# ---------- Exportar a PDF ----------
st.markdown("---")
st.subheader("Exportar a PDF")

def draw_pdf(buffer):
    c = rl_canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x0, y0 = 2*cm, 2*cm
    y = height - y0

    def line(txt, dy=14, size=11, bold=False, color=colors.black):
        nonlocal y
        if y < y0 + 2*cm:
            c.showPage()
            y = height - y0
            c.setFont("Helvetica", 11)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x0, y, txt)
        y -= dy

    line("Calculadora de Costos Agrícolas — Reporte", size=16, bold=True, dy=18)
    line(f"Escenario: {nombre_escenario}", bold=True)
    line(f"Fecha: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    line(f"Cultivo: {cultivo or '-'} | Moneda: {moneda} | Hectáreas: {hectareas}")
    line(f"Modo de captura: {st.session_state.modo}")
    line(" ", dy=8)

    line("Totales por hectárea", bold=True, dy=16)
    line(f"- Insumos (por ha): {money(insumos_ha, moneda)}")
    line(f"- Mano de obra (por ha): {money(mano_ha, moneda)}")
    line(f"- Otros (por ha): {money(otros_ha, moneda)}")
    line(f"- TOTAL (por ha): {money(total_ha, moneda)}", bold=True)
    line(" ", dy=8)
    line(f"Total temporada: {money(total_temporada, moneda)}", bold=True, dy=16)

    def dump_table(title, df, col_value_name):
        line(title, bold=True, dy=16)
        for _, row in df.iterrows():
            concept = str(row.get("Concepto", ""))
            val     = row.get(col_value_name, 0.0)
            notes   = str(row.get("Notas", ""))
            line(f"• {concept}: {money(float(val), moneda)}  [{notes}]")
        line(" ", dy=8)

    if st.session_state.modo == "Por hectárea":
        dump_table("Insumos (por ha)", st.session_state.insumos, "Costo por ha")
        dump_table("Mano de obra (por ha)", st.session_state.mano_obra, "Costo por ha")
        dump_table("Otros (por ha)", st.session_state.otros, "Costo por ha")
    else:
        dump_table("Insumos (totales temporada)", st.session_state.insumos, "Costo total (temporada)")
        dump_table("Mano de obra (totales temporada)", st.session_state.mano_obra, "Costo total (temporada)")
        dump_table("Otros (totales temporada)", st.session_state.otros, "Costo total (temporada)")

    line("Indicadores por kilo", bold=True, dy=16)
    line(f"- Producción total (kg): {produccion_total_kg:,.2f}")
    line(f"- Precio venta (por kg): {money(precio_venta_kg, moneda)}")
    line(f"- Costo por kg: {money(costo_por_kg, moneda)}", bold=True)
    line(f"- Ingreso total: {money(ingreso_total, moneda)}")
    color_margen = colors.green if margen_total >= 0 else colors.red
    line(f"- Margen total: {money(margen_total, moneda)}", color=color_margen)
    line(f"- Margen por kg: {money(margen_por_kg, moneda)}", color=color_margen)

    c.showPage()
    c.save()

nombre_pdf = st.text_input("Nombre del archivo PDF", value=f"{nombre_escenario}_costos.pdf")
if st.button("Generar PDF"):
    buf = io.BytesIO()
    draw_pdf(buf)
    st.download_button("⬇️ Descargar PDF", data=buf.getvalue(), file_name=nombre_pdf, mime="application/pdf")

st.caption("© 2025 Hydrobit — Este reporte es informativo y no sustituye un análisis financiero formal.")

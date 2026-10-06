import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date, timedelta
import io
import base64

# ReportLab para PDFs institucionales
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Componente opcional de firma táctil (con fallback a carga de imagen)
try:
    from streamlit_drawable_canvas import st_canvas
    CANVAS_DISPONIBLE = True
except ImportError:
    CANVAS_DISPONIBLE = False

# ----------------------------------------------------
# 1. CONFIGURACIÓN Y PROTECCIÓN ANTI-TRADUCTOR
# ----------------------------------------------------
st.set_page_config(
    page_title="Gestión de Equipos Biomédicos | ASAD IPS",
    page_icon="🩺",
    layout="wide"
)

st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>
        html, body, [class*="css"] { translate: no !important; }
        .main-title { font-size: 26px; font-weight: bold; color: #1F4E79; margin-bottom: 2px; }
        .sub-title { font-size: 14px; color: #555; margin-bottom: 20px; }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-title">🩺 Sistema de Control y Calidad de Equipos Biomédicos</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Gestión de Hojas de Vida (RF-EB-FR-001), Reportes de Mantenimiento (RF-EB-FR-005) y Control Metrológico.</div>', unsafe_allow_html=True)

# ----------------------------------------------------
# 2. BASE DE DATOS SQLITE INSTITUCIONAL
# ----------------------------------------------------
DB_NAME = "biomedico.db"

def get_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    conn = get_db()
    c = conn.cursor()
    # Tabla RF-EB-FR-001 (Hoja de Vida)
    c.execute('''
    CREATE TABLE IF NOT EXISTS equipos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        placa TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        marca TEXT,
        modelo TEXT,
        serie TEXT,
        registro_invima TEXT,
        clasificacion_riesgo TEXT,
        clasificacion_biomedica TEXT,
        sede TEXT,
        ubicacion TEXT,
        estado TEXT DEFAULT 'Operativo',
        frecuencia_mantenimiento TEXT DEFAULT 'Semestral',
        fecha_adquisicion TEXT,
        fecha_ultimo_mantenimiento TEXT,
        fecha_proximo_mantenimiento TEXT,
        requiere_calibracion TEXT DEFAULT 'NO',
        fecha_proxima_calibracion TEXT,
        accesorios TEXT,
        observaciones TEXT
    )
    ''')
    # Tabla RF-EB-FR-005 (Reportes de Servicio Técnico)
    c.execute('''
    CREATE TABLE IF NOT EXISTS reportes_mantenimiento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipo_id INTEGER,
        numero_reporte TEXT,
        fecha_servicio TEXT,
        tipo_servicio TEXT,
        descripcion_actividades TEXT,
        repuestos_utilizados TEXT,
        herramientas_patron TEXT,
        estado_equipo_final TEXT,
        tecnico_responsable TEXT,
        registro_profesional TEXT,
        recibido_por TEXT,
        firma_tecnico TEXT,
        firma_recibido TEXT,
        FOREIGN KEY (equipo_id) REFERENCES equipos (id)
    )
    ''')
    conn.commit()
    conn.close()

inicializar_bd()

def cargar_equipos():
    conn = get_db()
    df = pd.read_sql_query("SELECT * FROM equipos ORDER BY nombre ASC", conn)
    conn.close()
    return df

def cargar_reportes(equipo_id=None):
    conn = get_db()
    if equipo_id:
        query = f"SELECT * FROM reportes_mantenimiento WHERE equipo_id = {equipo_id} ORDER BY fecha_servicio DESC"
    else:
        query = "SELECT r.*, e.placa, e.nombre FROM reportes_mantenimiento r LEFT JOIN equipos e ON r.equipo_id = e.id ORDER BY r.fecha_servicio DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

df_equipos = cargar_equipos()

# ----------------------------------------------------
# 3. GENERADORES DE PDF OFICIALES (REPORTLAB)
# ----------------------------------------------------
def generar_pdf_hoja_vida(eq):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, alignment=1, textColor=colors.HexColor('#1F4E79'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=1, textColor=colors.HexColor('#333333'))
    cell_hdr = ParagraphStyle('CHdr', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#FFFFFF'))
    cell_txt = ParagraphStyle('CTxt', parent=styles['Normal'], fontName='Helvetica', fontSize=8)

    story = []

    # Encabezado Oficial
    header_data = [
        [Paragraph("<b>ASAD ASISTENCIA EN SALUD DOMICILIARIA SAS</b><br/>RECURSOS FÍSICOS - GESTIÓN TECNOLÓGICA", sub_style),
         Paragraph("<b>HOJA DE VIDA DE EQUIPO BIOMÉDICO</b><br/>CÓDIGO: RF-EB-FR-001", title_style)]
    ]
    t_hdr = Table(header_data, colWidths=[270, 270])
    t_hdr.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#1F4E79')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_hdr)
    story.append(Spacer(1, 10))

    # 1. Identificación
    story.append(Paragraph("<b>1. IDENTIFICACIÓN Y UBICACIÓN DEL ACTIVO</b>", ParagraphStyle('S1', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1F4E79'))))
    story.append(Spacer(1, 4))
    
    data_id = [
        [Paragraph("<b>NOMBRE EQUIPO:</b>", cell_txt), Paragraph(str(eq.get('nombre', '')), cell_txt), Paragraph("<b>PLACA / ACTIVO:</b>", cell_txt), Paragraph(str(eq.get('placa', '')), cell_txt)],
        [Paragraph("<b>MARCA:</b>", cell_txt), Paragraph(str(eq.get('marca', '')), cell_txt), Paragraph("<b>MODELO:</b>", cell_txt), Paragraph(str(eq.get('modelo', '')), cell_txt)],
        [Paragraph("<b>SERIE:</b>", cell_txt), Paragraph(str(eq.get('serie', '')), cell_txt), Paragraph("<b>REG. INVIMA:</b>", cell_txt), Paragraph(str(eq.get('registro_invima', '')), cell_txt)],
        [Paragraph("<b>SEDE:</b>", cell_txt), Paragraph(str(eq.get('sede', '')), cell_txt), Paragraph("<b>SERVICIO / ÁREA:</b>", cell_txt), Paragraph(str(eq.get('ubicacion', '')), cell_txt)],
        [Paragraph("<b>ESTADO ACTUAL:</b>", cell_txt), Paragraph(str(eq.get('estado', '')), cell_txt), Paragraph("<b>FECHA ADQUISICIÓN:</b>", cell_txt), Paragraph(str(eq.get('fecha_adquisicion', '')), cell_txt)],
    ]
    t_id = Table(data_id, colWidths=[100, 170, 100, 170])
    t_id.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F2F2F2')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F2F2F2')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_id)
    story.append(Spacer(1, 10))

    # 2. Clasificación Técnica y Metrológica
    story.append(Paragraph("<b>2. CLASIFICACIÓN TÉCNICA, RIESGO Y CONTROL METROLÓGICO</b>", ParagraphStyle('S2', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1F4E79'))))
    story.append(Spacer(1, 4))
    
    data_riesgo = [
        [Paragraph("<b>CLASIFICACIÓN RIESGO:</b>", cell_txt), Paragraph(str(eq.get('clasificacion_riesgo', '')), cell_txt), Paragraph("<b>TIPO BIOMÉDICO:</b>", cell_txt), Paragraph(str(eq.get('clasificacion_biomedica', '')), cell_txt)],
        [Paragraph("<b>FREQ. MANTENIMIENTO:</b>", cell_txt), Paragraph(str(eq.get('frecuencia_mantenimiento', '')), cell_txt), Paragraph("<b>REQUIERE CALIBRACIÓN:</b>", cell_txt), Paragraph(str(eq.get('requiere_calibracion', '')), cell_txt)],
        [Paragraph("<b>ÚLTIMO MANTENIMIENTO:</b>", cell_txt), Paragraph(str(eq.get('fecha_ultimo_mantenimiento', '')), cell_txt), Paragraph("<b>PRÓXIMO MANTENIMIENTO:</b>", cell_txt), Paragraph(str(eq.get('fecha_proximo_mantenimiento', '')), cell_txt)],
        [Paragraph("<b>PRÓXIMA CALIBRACIÓN:</b>", cell_txt), Paragraph(str(eq.get('fecha_proxima_calibracion', '') or 'N/A'), cell_txt), Paragraph("<b>ACCESORIOS:</b>", cell_txt), Paragraph(str(eq.get('accesorios', '') or 'Ninguno'), cell_txt)],
    ]
    t_riesgo = Table(data_riesgo, colWidths=[110, 160, 120, 150])
    t_riesgo.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F2F2F2')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F2F2F2')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_riesgo)
    story.append(Spacer(1, 10))

    # 3. Observaciones
    story.append(Paragraph("<b>3. OBSERVACIONES GENERALES Y RECOMENDACIONES</b>", ParagraphStyle('S3', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1F4E79'))))
    story.append(Spacer(1, 4))
    obs_txt = Paragraph(str(eq.get('observaciones', 'Sin observaciones adicionales registradas.')), cell_txt)
    t_obs = Table([[obs_txt]], colWidths=[540])
    t_obs.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_obs)

    doc.build(story)
    buffer.seek(0)
    return buffer

def generar_pdf_reporte_servicio(rep, eq):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, alignment=1, textColor=colors.HexColor('#1F4E79'))
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, alignment=1, textColor=colors.HexColor('#333333'))
    cell_txt = ParagraphStyle('CTxt', parent=styles['Normal'], fontName='Helvetica', fontSize=8)

    story = []

    # Encabezado
    header_data = [
        [Paragraph("<b>ASAD ASISTENCIA EN SALUD DOMICILIARIA SAS</b><br/>GESTIÓN TECNOLÓGICA Y MANTENIMIENTO", sub_style),
         Paragraph(f"<b>REPORTE DE SERVICIO TÉCNICO</b><br/>CÓDIGO: RF-EB-FR-005<br/><b>N°: {rep.get('numero_reporte', 'S/N')}</b>", title_style)]
    ]
    t_hdr = Table(header_data, colWidths=[270, 270])
    t_hdr.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#1F4E79')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_hdr)
    story.append(Spacer(1, 10))

    # Datos Equipo
    story.append(Paragraph("<b>1. DATOS DEL EQUIPO INTERVENIDO</b>", ParagraphStyle('S1', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1F4E79'))))
    story.append(Spacer(1, 4))
    data_eq = [
        [Paragraph("<b>EQUIPO:</b>", cell_txt), Paragraph(str(eq.get('nombre', '')), cell_txt), Paragraph("<b>PLACA:</b>", cell_txt), Paragraph(str(eq.get('placa', '')), cell_txt)],
        [Paragraph("<b>MARCA / MODELO:</b>", cell_txt), Paragraph(f"{eq.get('marca', '')} / {eq.get('modelo', '')}", cell_txt), Paragraph("<b>SERIE:</b>", cell_txt), Paragraph(str(eq.get('serie', '')), cell_txt)],
        [Paragraph("<b>UBICACIÓN:</b>", cell_txt), Paragraph(f"{eq.get('sede', '')} - {eq.get('ubicacion', '')}", cell_txt), Paragraph("<b>FECHA SERVICIO:</b>", cell_txt), Paragraph(str(rep.get('fecha_servicio', '')), cell_txt)],
        [Paragraph("<b>TIPO SERVICIO:</b>", cell_txt), Paragraph(str(rep.get('tipo_servicio', '')), cell_txt), Paragraph("<b>ESTADO FINAL:</b>", cell_txt), Paragraph(str(rep.get('estado_equipo_final', '')), cell_txt)],
    ]
    t_eq = Table(data_eq, colWidths=[100, 170, 100, 170])
    t_eq.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F2F2F2')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F2F2F2')),
    ]))
    story.append(t_eq)
    story.append(Spacer(1, 10))

    # Detalle Técnico
    story.append(Paragraph("<b>2. ACTIVIDADES TÉCNICAS REALIZADAS Y DIAGNÓSTICO</b>", ParagraphStyle('S2', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1F4E79'))))
    story.append(Spacer(1, 4))
    act_txt = Paragraph(str(rep.get('descripcion_actividades', '')), cell_txt)
    t_act = Table([[act_txt]], colWidths=[540])
    t_act.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BOTTOMPADDING', (0,0), (-1,-1), 16),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_act)
    story.append(Spacer(1, 10))

    # Repuestos y Patrón
    data_rep = [
        [Paragraph("<b>REPUESTOS / INSUMOS:</b>", cell_txt), Paragraph(str(rep.get('repuestos_utilizados', '') or 'Ninguno'), cell_txt)],
        [Paragraph("<b>HERRAMIENTAS / PATRÓN:</b>", cell_txt), Paragraph(str(rep.get('herramientas_patron', '') or 'Herramientas estándar'), cell_txt)]
    ]
    t_rep = Table(data_rep, colWidths=[140, 400])
    t_rep.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F2F2F2')),
    ]))
    story.append(t_rep)
    story.append(Spacer(1, 15))

    # Firmas
    f_tec = Paragraph(f"<b>TÉCNICO / INGENIERO BIOMÉDICO</b><br/>{rep.get('tecnico_responsable', '')}<br/>Reg. Prof: {rep.get('registro_profesional', 'N/A')}", cell_txt)
    f_rec = Paragraph(f"<b>RECIBIDO A SATISFACCIÓN</b><br/>{rep.get('recibido_por', '')}<br/>ASAD IPS", cell_txt)
    
    t_firmas = Table([[f_tec, f_rec]], colWidths=[270, 270])
    t_firmas.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#1F4E79')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 35), # Espacio para firma
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_firmas)

    doc.build(story)
    buffer.seek(0)
    return buffer

# ----------------------------------------------------
# 4. TABLERO DE CONTROL Y SEMAFORIZACIÓN (CALIDAD)
# ----------------------------------------------------
st.write("---")
hoy = date.today()
en_30_dias = hoy + timedelta(days=30)

tot_activos = len(df_equipos)
operativos = 0
vencidos_mant = 0
proximos_mant = 0

if not df_equipos.empty:
    operativos = (df_equipos['estado'].str.upper() == 'OPERATIVO').sum()
    for _, r in df_equipos.iterrows():
        f_p = r.get('fecha_proximo_mantenimiento')
        if f_p and str(f_p).strip() != '' and str(f_p) != 'None':
            try:
                dt_p = pd.to_datetime(f_p).date()
                if dt_p < hoy:
                    vencidos_mant += 1
                elif hoy <= dt_p <= en_30_dias:
                    proximos_mant += 1
            except:
                pass

m1, m2, m3, m4 = st.columns(4)
m1.metric("📦 Total Equipos", tot_activos)
m2.metric("✅ Estado Operativo", f"{operativos} / {tot_activos}")
m3.metric("🚨 Mantenimientos Vencidos", vencidos_mant, delta_color="inverse")
m4.metric("⚠️ Vencen en < 30 Días", proximos_mant, delta_color="inverse")
st.write("---")

# ----------------------------------------------------
# 5. PESTAÑAS PRINCIPALES DEL SISTEMA
# ----------------------------------------------------
tab_inv, tab_reg, tab_rep, tab_masivo = st.tabs([
    "📋 Inventario & Hojas de Vida (RF-EB-FR-001)",
    "➕ Registrar Equipo (RF-EB-FR-001)",
    "🛠️ Reportes de Servicio Técnico (RF-EB-FR-005)",
    "📂 Carga Masiva y Respaldo Excel"
])

# ==========================================
# PESTAÑA 1: INVENTARIO & HOJA DE VIDA
# ==========================================
with tab_inv:
    st.subheader("Catálogo de Equipos Biomédicos")
    
    if df_equipos.empty:
        st.warning("No hay equipos registrados en la base de datos. Puedes cargar tu inventario en la pestaña 'Carga Masiva y Respaldo Excel' o registrar uno nuevo.")
    else:
        c_b1, c_b2, c_b3 = st.columns([2, 1, 1])
        with c_b1:
            txt_b = st.text_input("🔍 Buscar por Placa, Nombre, Serie, Marca o INVIMA:", "")
        with c_b2:
            sedes_list = ["Todas"] + sorted(list(df_equipos['sede'].dropna().unique()))
            sel_sede = st.selectbox("Sede:", sedes_list)
        with c_b3:
            est_list = ["Todos"] + sorted(list(df_equipos['estado'].dropna().unique()))
            sel_est = st.selectbox("Estado:", est_list)

        df_show = df_equipos.copy()
        if txt_b.strip():
            b = txt_b.strip().upper()
            mask = df_show.astype(str).apply(lambda r: r.str.upper().str.contains(b, na=False)).any(axis=1)
            df_show = df_show[mask]
        if sel_sede != "Todas":
            df_show = df_show[df_show['sede'] == sel_sede]
        if sel_est != "Todos":
            df_show = df_show[df_show['estado'] == sel_est]

        st.dataframe(df_show[['placa', 'nombre', 'marca', 'modelo', 'serie', 'registro_invima', 'clasificacion_riesgo', 'sede', 'ubicacion', 'estado', 'fecha_proximo_mantenimiento']], use_container_width=True)

        st.write("---")
        st.subheader("📄 Generar Hoja de Vida Oficial (RF-EB-FR-001)")
        
        eq_map = {f"{r['placa']} - {r['nombre']} ({r['sede']})": r['id'] for _, r in df_show.iterrows()}
        if eq_map:
            sel_eq_str = st.selectbox("Selecciona un equipo para descargar su Hoja de Vida:", list(eq_map.keys()))
            id_sel = eq_map[sel_eq_str]
            eq_dict = df_equipos[df_equipos['id'] == id_sel].iloc[0].to_dict()

            pdf_hv = generar_pdf_hoja_vida(eq_dict)
            st.download_button(
                label=f"📥 Descargar Hoja de Vida PDF ({eq_dict['placa']})",
                data=pdf_hv,
                file_name=f"HOJA_DE_VIDA_{eq_dict['placa']}.pdf",
                mime="application/pdf",
                type="primary"
            )

# ==========================================
# PESTAÑA 2: REGISTRO DE EQUIPO (RF-EB-FR-001)
# ==========================================
with tab_reg:
    st.subheader("Formulario de Registro Técnico RF-EB-FR-001")
    with st.form("form_nuevo_activo", clear_on_submit=True):
        st.markdown("##### 1. Datos de Identificación")
        r1, r2, r3 = st.columns(3)
        placa = r1.text_input("Placa / Activo Fijo *")
        nombre = r2.text_input("Nombre del Equipo *")
        marca = r3.text_input("Marca")

        r4, r5, r6 = st.columns(3)
        modelo = r4.text_input("Modelo")
        serie = r5.text_input("Número de Serie")
        invima = r6.text_input("Registro Sanitario INVIMA")

        st.markdown("##### 2. Ubicación y Clasificación Normativa")
        r7, r8, r9 = st.columns(3)
        riesgo = r7.selectbox("Clasificación del Riesgo", ["I (Bajo Riesgo)", "IIA (Riesgo Moderado)", "IIB (Alto Riesgo)", "III (Muy Alto Riesgo)"])
        biomed = r8.selectbox("Clasificación Biomédica", ["Diagnóstico", "Tratamiento", "Rehabilitación", "Soporte Vital", "Monitoreo"])
        sede = r9.selectbox("Sede", ["Ibagué", "Fusagasugá", "Otra"])

        r10, r11, r12 = st.columns(3)
        ubicacion = r10.text_input("Ubicación / Área de Servicio")
        estado = r11.selectbox("Estado Inicial", ["Operativo", "En Mantenimiento", "Fuera de Servicio", "En Calibración"])
        frec_mant = r12.selectbox("Frecuencia Mantenimiento Preventivo", ["Semestral", "Anual", "Cuatrimestral", "Trimestral"])

        st.markdown("##### 3. Fechas de Mantenimiento y Calibración Metrológica")
        r13, r14, r15 = st.columns(3)
        f_adq = r13.date_input("Fecha de Adquisición", value=date.today())
        f_ult = r14.date_input("Último Mantenimiento Realizado", value=date.today())
        f_prox = r15.date_input("Próximo Mantenimiento Programado", value=date.today() + timedelta(days=180))

        r16, r17 = st.columns(2)
        req_cal = r16.selectbox("¿Requiere Calibración Metrológica?", ["NO", "SI"])
        f_cal = r17.date_input("Fecha Próxima Calibración", value=date.today() + timedelta(days=365))

        accesorios = st.text_input("Accesorios Incluidos / Sensores / Cables")
        observaciones = st.text_area("Observaciones Técnicas / Fabricante")

        guardar_eq = st.form_submit_button("💾 Guardar Hoja de Vida en Base de Datos", type="primary")

        if guardar_eq:
            if not placa.strip() or not nombre.strip():
                st.error("Los campos 'Placa' y 'Nombre del Equipo' son obligatorios.")
            else:
                try:
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute('''
                    INSERT INTO equipos (
                        placa, nombre, marca, modelo, serie, registro_invima,
                        clasificacion_riesgo, clasificacion_biomedica, sede, ubicacion,
                        estado, frecuencia_mantenimiento, fecha_adquisicion,
                        fecha_ultimo_mantenimiento, fecha_proximo_mantenimiento,
                        requiere_calibracion, fecha_proxima_calibracion, accesorios, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        placa.strip().upper(), nombre.strip().upper(), marca.strip().upper(),
                        modelo.strip().upper(), serie.strip().upper(), invima.strip().upper(),
                        riesgo, biomed, sede, ubicacion.strip().upper(), estado, frec_mant,
                        f_adq.strftime('%Y-%m-%d'), f_ult.strftime('%Y-%m-%d'), f_prox.strftime('%Y-%m-%d'),
                        req_cal, f_cal.strftime('%Y-%m-%d') if req_cal == "SI" else "",
                        accesorios.strip(), observaciones.strip()
                    ))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Hoja de Vida creada exitosamente para '{nombre.upper()}' (Placa: {placa.upper()}).")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Ya existe un equipo registrado con la placa '{placa.strip().upper()}'.")
                except Exception as e:
                    st.error(f"Error al registrar: {e}")

# ==========================================
# PESTAÑA 3: REPORTES DE MANTENIMIENTO (RF-EB-FR-005)
# ==========================================
with tab_rep:
    st.subheader("Reporte Técnico de Mantenimiento RF-EB-FR-005")
    
    if df_equipos.empty:
        st.info("Primero registra equipos para poder generar reportes de servicio técnico.")
    else:
        st.markdown("#### Nuevo Reporte de Intervención")
        with st.form("form_reporte_servicio"):
            s1, s2, s3 = st.columns(3)
            eq_opciones = {f"{r['placa']} - {r['nombre']}": r['id'] for _, r in df_equipos.iterrows()}
            eq_sel_rep = s1.selectbox("Equipo Intervenido *", list(eq_opciones.keys()))
            num_rep = s2.text_input("Número de Reporte / OT *", value=f"OT-{datetime.now().strftime('%y%m%d%H%M')}")
            f_serv = s3.date_input("Fecha del Servicio *", value=date.today())

            s4, s5, s6 = st.columns(3)
            tipo_serv = s4.selectbox("Tipo de Servicio", ["Preventivo", "Correctivo", "Calibración", "Inspección Locativa / Eléctrica", "Instalación"])
            est_final = s5.selectbox("Estado Final del Equipo", ["Operativo", "En Mantenimiento", "Fuera de Servicio", "Baja Sugerida"])
            dias_prox = 180 if tipo_serv == "Preventivo" else 90
            nueva_fecha_prox = s6.date_input("Próximo Mantenimiento Sugerido", value=date.today() + timedelta(days=dias_prox))

            desc_act = st.text_area("Descripción de Actividades Realizadas, Pruebas y Diagnóstico *")
            repuestos = st.text_input("Repuestos o Insumos Instalados (dejar vacío si no aplica)")
            herramientas = st.text_input("Herramientas / Equipo Patrón Utilizado (Simulador, Multímetro, etc.)")

            s7, s8, s9 = st.columns(3)
            tec_resp = s7.text_input("Técnico / Ingeniero Responsable *", value="HAROL CAMILO MONTOYA")
            reg_prof = s8.text_input("Registro Profesional / Matrícula")
            recib_por = s9.text_input("Recibido a Satisfacción por (Nombre y Cargo) *", value="Coordinador de Recursos Físicos")

            btn_rep = st.form_submit_button("💾 Guardar Reporte y Actualizar Equipo", type="primary")

            if btn_rep:
                if not desc_act.strip() or not tec_resp.strip():
                    st.error("La descripción de actividades y el nombre del técnico son obligatorios.")
                else:
                    id_eq_sel = eq_opciones[eq_sel_rep]
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute('''
                    INSERT INTO reportes_mantenimiento (
                        equipo_id, numero_reporte, fecha_servicio, tipo_servicio,
                        descripcion_actividades, repuestos_utilizados, herramientas_patron,
                        estado_equipo_final, tecnico_responsable, registro_profesional, recibido_por
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        id_eq_sel, num_rep.strip().upper(), f_serv.strftime('%Y-%m-%d'),
                        tipo_serv, desc_act.strip(), repuestos.strip(), herramientas.strip(),
                        est_final, tec_resp.strip().upper(), reg_prof.strip().upper(), recib_por.strip().upper()
                    ))
                    # Actualiza automáticamente la hoja de vida del equipo
                    cur.execute('''
                    UPDATE equipos SET
                        estado = ?,
                        fecha_ultimo_mantenimiento = ?,
                        fecha_proximo_mantenimiento = ?
                    WHERE id = ?
                    ''', (est_final, f_serv.strftime('%Y-%m-%d'), nueva_fecha_prox.strftime('%Y-%m-%d'), id_eq_sel))
                    conn.commit()
                    conn.close()
                    st.success("✅ Reporte de servicio técnico guardado y Hoja de Vida actualizada.")
                    st.rerun()

        st.write("---")
        st.markdown("#### Historial de Reportes Generados")
        df_reps = cargar_reportes()
        if not df_reps.empty:
            st.dataframe(df_reps[['numero_reporte', 'fecha_servicio', 'placa', 'nombre', 'tipo_servicio', 'estado_equipo_final', 'tecnico_responsable']], use_container_width=True)

            rep_map = {f"{r['numero_reporte']} - {r['placa']} ({r['fecha_servicio']})": r['id'] for _, r in df_reps.iterrows()}
            sel_r_str = st.selectbox("Selecciona un reporte para descargar en PDF:", list(rep_map.keys()))
            id_rep_sel = rep_map[sel_r_str]
            r_data = df_reps[df_reps['id'] == id_rep_sel].iloc[0].to_dict()
            eq_rel = df_equipos[df_equipos['id'] == r_data['equipo_id']].iloc[0].to_dict()

            pdf_ot = generar_pdf_reporte_servicio(r_data, eq_rel)
            st.download_button(
                label=f"📥 Descargar Reporte Técnico PDF ({r_data['numero_reporte']})",
                data=pdf_ot,
                file_name=f"REPORTE_TECNICO_{r_data['numero_reporte']}.pdf",
                mime="application/pdf"
            )

# ==========================================
# PESTAÑA 4: CARGA MASIVA Y RESPALDO EXCEL
# ==========================================
with tab_masivo:
    st.subheader("Importación y Exportación Masiva")
    st.info("Sube tu archivo Excel para cargar de una vez todos tus equipos biomédicos sin tener que digitarlos manualmente.")

    c_up, c_down = st.columns(2)
    with c_up:
        st.markdown("##### 📥 Cargar Inventario desde Excel")
        f_excel = st.file_uploader("Selecciona archivo Excel (.xlsx / .xls)", type=["xlsx", "xls"], key="carga_masiva")
        if f_excel:
            if st.button("🚀 Procesar e Importar a Base de Datos", type="primary"):
                try:
                    df_in = pd.read_excel(f_excel)
                    conn = get_db()
                    cur = conn.cursor()
                    insertados = 0
                    actualizados = 0

                    for _, row in df_in.iterrows():
                        # Detecta nombres de columna flexibles
                        placa_val = str(row.get('PLACA') or row.get('Placa') or row.get('ACTIVO') or '').strip().upper()
                        nombre_val = str(row.get('NOMBRE') or row.get('Nombre') or row.get('EQUIPO') or '').strip().upper()
                        if not placa_val or placa_val in ['NAN', 'NONE', '']: continue

                        marca_val = str(row.get('MARCA') or row.get('Marca') or '').strip().upper()
                        modelo_val = str(row.get('MODELO') or row.get('Modelo') or '').strip().upper()
                        serie_val = str(row.get('SERIE') or row.get('Serie') or '').strip().upper()
                        invima_val = str(row.get('INVIMA') or row.get('REGISTRO INVIMA') or '').strip().upper()
                        riesgo_val = str(row.get('RIESGO') or row.get('CLASIFICACION RIESGO') or 'IIA (Riesgo Moderado)').strip()
                        biomed_val = str(row.get('BIOMEDICO') or row.get('TIPO') or 'Diagnóstico').strip()
                        sede_val = str(row.get('SEDE') or row.get('Sede') or 'Ibagué').strip()
                        ubica_val = str(row.get('UBICACION') or row.get('Ubicacion') or row.get('SERVICIO') or '').strip().upper()
                        estado_val = str(row.get('ESTADO') or row.get('Estado') or 'Operativo').strip()

                        # Verifica si existe para insertar o actualizar
                        cur.execute("SELECT id FROM equipos WHERE placa = ?", (placa_val,))
                        existe = cur.fetchone()
                        if existe:
                            cur.execute('''
                            UPDATE equipos SET
                                nombre=?, marca=?, modelo=?, serie=?, registro_invima=?,
                                clasificacion_riesgo=?, clasificacion_biomedica=?, sede=?, ubicacion=?, estado=?
                            WHERE placa=?
                            ''', (nombre_val, marca_val, modelo_val, serie_val, invima_val, riesgo_val, biomed_val, sede_val, ubica_val, estado_val, placa_val))
                            actualizados += 1
                        else:
                            cur.execute('''
                            INSERT INTO equipos (
                                placa, nombre, marca, modelo, serie, registro_invima,
                                clasificacion_riesgo, clasificacion_biomedica, sede, ubicacion, estado,
                                fecha_proximo_mantenimiento
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (placa_val, nombre_val, marca_val, modelo_val, serie_val, invima_val, riesgo_val, biomed_val, sede_val, ubica_val, estado_val, (date.today() + timedelta(days=180)).strftime('%Y-%m-%d')))
                            insertados += 1

                    conn.commit()
                    conn.close()
                    st.success(f"✅ Proceso finalizado: {insertados} equipos nuevos agregados y {actualizados} actualizados.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error importando archivo Excel: {e}")

    with c_down:
        st.markdown("##### 📤 Exportar Base de Datos Completa")
        if not df_equipos.empty:
            buf_exp = io.BytesIO()
            with pd.ExcelWriter(buf_exp, engine='openpyxl') as writer:
                df_equipos.to_excel(writer, sheet_name='INVENTARIO_EQUIPOS', index=False)
                cargar_reportes().to_excel(writer, sheet_name='HISTORIAL_REPORTES', index=False)
            buf_exp.seek(0)

            st.download_button(
                label="📥 Descargar Base Completa en Excel (.xlsx)",
                data=buf_exp,
                file_name=f"ASAD_INVENTARIO_BIOMEDICO_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
        else:
            st.info("No hay datos para exportar actualmente.")

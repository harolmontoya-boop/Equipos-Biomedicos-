import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import io

# 1. Configuración de la página
st.set_page_config(
    page_title="Control y Gestión de Equipos Biomédicos",
    page_icon="🩺",
    layout="wide"
)

# 2. Bloqueo anti-traductor de Google Chrome (Evita fallos de React/removeChild)
st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>
        html, body, [class*="css"] {
            translate: no !important;
        }
        .main-header {
            font-size: 26px;
            font-weight: bold;
            color: #1F4E79;
            margin-bottom: 5px;
        }
        .sub-header {
            font-size: 14px;
            color: #555;
            margin-bottom: 20px;
        }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<div class="main-header">🩺 Sistema de Control y Gestión de Equipos Biomédicos</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Inventario centralizado, trazabilidad de mantenimiento preventivo y control metrológico.</div>', unsafe_allow_html=True)

# 3. Conexión y gestión de la Base de Datos SQLite
DB_NAME = "biomedico.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    conn = get_connection()
    cursor = conn.cursor()
    # Verifica tablas existentes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall() if r[0] != 'sqlite_sequence']
    
    # Si la tabla equipos no existe, se inicializa con el esquema estándar
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS equipos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        placa TEXT UNIQUE,
        nombre TEXT NOT NULL,
        marca TEXT,
        modelo TEXT,
        serie TEXT,
        registro_invima TEXT,
        clasificacion_riesgo TEXT,
        sede TEXT,
        ubicacion TEXT,
        estado TEXT,
        fecha_ultimo_mantenimiento TEXT,
        fecha_proximo_mantenimiento TEXT,
        observaciones TEXT
    )
    ''')
    conn.commit()
    conn.close()

inicializar_bd()

def obtener_datos():
    conn = get_connection()
    # Detecta qué tabla contiene los equipos
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tablas = [r[0] for r in cursor.fetchall() if r[0] != 'sqlite_sequence']
    
    tabla_objetivo = 'equipos' if 'equipos' in tablas else (tablas[0] if tablas else 'equipos')
    df = pd.read_sql_query(f"SELECT * FROM {tabla_objetivo}", conn)
    conn.close()
    return df, tabla_objetivo

df_equipos, tabla_activa = obtener_datos()

# 4. Métricas Principales (KPIs)
st.write("---")
c1, c2, c3, c4 = st.columns(4)

tot_equipos = len(df_equipos)
operativos = 0
en_mantenimiento = 0
vencidos = 0

hoy = date.today()

if not df_equipos.empty:
    col_estado = [c for c in df_equipos.columns if 'ESTADO' in c.upper()]
    if col_estado:
        operativos = (df_equipos[col_estado[0]].astype(str).str.upper() == 'OPERATIVO').sum()
        en_mantenimiento = (df_equipos[col_estado[0]].astype(str).str.upper().isin(['EN MANTENIMIENTO', 'FUERA DE SERVICIO', 'EN REPARACION'])).sum()
    
    col_prox = [c for c in df_equipos.columns if 'PROXIMO' in c.upper() or 'PROX' in c.upper()]
    if col_prox:
        for val in df_equipos[col_prox[0]].dropna():
            try:
                f_dt = pd.to_datetime(val).date()
                if f_dt < hoy:
                    vencidos += 1
            except:
                pass

c1.metric("📦 Total Equipos", tot_equipos)
c2.metric("✅ Operativos", operativos)
c3.metric("⚠️ En Mantenimiento / Revisión", en_mantenimiento)
c4.metric("🚨 Mantenimientos Vencidos", vencidos, delta_color="inverse")
st.write("---")

# 5. Estructura de Pestañas
tab_inventario, tab_registro, tab_mantenimiento = st.tabs([
    "📋 Inventario y Consulta",
    "➕ Registrar Nuevo Equipo",
    "🛠️ Actualizar Mantenimiento / Estado"
])

# ----------------------------------------------------
# PESTAÑA 1: INVENTARIO Y FILTROS
# ----------------------------------------------------
with tab_inventario:
    st.subheader("Búsqueda y Filtros de Inventario")
    
    if df_equipos.empty:
        st.info("No hay registros en la base de datos. Agrega el primer equipo en la pestaña 'Registrar Nuevo Equipo'.")
    else:
        f1, f2, f3, f4 = st.columns(4)
        
        # Filtro por texto
        with f1:
            busqueda = st.text_input("🔍 Buscar (Placa, Nombre, Serie, Marca):", "")
            
        # Filtro Sede
        col_sede = [c for c in df_equipos.columns if 'SEDE' in c.upper()]
        with f2:
            if col_sede:
                sedes = ["Todas"] + sorted(list(df_equipos[col_sede[0]].dropna().unique()))
                sel_sede = st.selectbox("📍 Sede:", sedes)
            else:
                sel_sede = "Todas"

        # Filtro Estado
        col_est = [c for c in df_equipos.columns if 'ESTADO' in c.upper()]
        with f3:
            if col_est:
                estados = ["Todos"] + sorted(list(df_equipos[col_est[0]].dropna().unique()))
                sel_est = st.selectbox("⚙️ Estado Operativo:", estados)
            else:
                sel_est = "Todos"

        # Filtro Riesgo
        col_riesgo = [c for c in df_equipos.columns if 'RIESGO' in c.upper()]
        with f4:
            if col_riesgo:
                riesgos = ["Todos"] + sorted(list(df_equipos[col_riesgo[0]].dropna().unique()))
                sel_riesgo = st.selectbox("🏷️ Clasificación de Riesgo:", riesgos)
            else:
                sel_riesgo = "Todos"

        # Aplicación de Filtros
        df_filtrado = df_equipos.copy()

        if busqueda.strip():
            b = busqueda.strip().upper()
            mask = df_filtrado.astype(str).apply(lambda row: row.str.upper().str.contains(b, na=False)).any(axis=1)
            df_filtrado = df_filtrado[mask]

        if col_sede and sel_sede != "Todas":
            df_filtrado = df_filtrado[df_filtrado[col_sede[0]] == sel_sede]

        if col_est and sel_est != "Todos":
            df_filtrado = df_filtrado[df_filtrado[col_est[0]] == sel_est]

        if col_riesgo and sel_riesgo != "Todos":
            df_filtrado = df_filtrado[df_filtrado[col_riesgo[0]] == sel_riesgo]

        st.caption(f"Mostrando {len(df_filtrado)} de {len(df_equipos)} equipos registrados.")
        st.dataframe(df_filtrado, use_container_width=True)

        # Descarga en Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_filtrado.to_excel(writer, index=False, sheet_name='Inventario_Biomedico')
        buffer.seek(0)

        st.download_button(
            label="📥 Descargar Reporte Filtrado en Excel (.xlsx)",
            data=buffer,
            file_name=f"INVENTARIO_BIOMEDICO_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ----------------------------------------------------
# PESTAÑA 2: REGISTRO DE NUEVO EQUIPO
# ----------------------------------------------------
with tab_registro:
    st.subheader("Registro de Hoja de Vida / Equipo Biomédico")
    with st.form("form_nuevo_equipo", clear_on_submit=True):
        r1, r2, r3 = st.columns(3)
        with r1:
            placa = st.text_input("Placa / Activo Fijo *")
            nombre = st.text_input("Nombre del Equipo *")
            marca = st.text_input("Marca")
        with r2:
            modelo = st.text_input("Modelo")
            serie = st.text_input("Número de Serie")
            invima = st.text_input("Registro Sanitario INVIMA")
        with r3:
            riesgo = st.selectbox("Clasificación del Riesgo", ["I (Bajo Riesgo)", "IIA (Riesgo Moderado)", "IIB (Alto Riesgo)", "III (Muy Alto Riesgo)"])
            sede = st.selectbox("Sede", ["Ibagué", "Fusagasugá", "Otra"])
            ubicacion = st.text_input("Ubicación / Servicio")

        r4, r5, r6 = st.columns(3)
        with r4:
            estado = st.selectbox("Estado Operativo", ["Operativo", "En Mantenimiento", "Fuera de Servicio", "Baja"])
        with r5:
            ult_mant = st.date_input("Fecha Último Mantenimiento", value=date.today())
        with r6:
            prox_mant = st.date_input("Fecha Próximo Mantenimiento", value=date.today())

        observaciones = st.text_area("Observaciones Técnicas / Accesorios")
        
        btn_guardar = st.form_submit_button("💾 Guardar Equipo en Base de Datos", type="primary")

        if btn_guardar:
            if not placa.strip() or not nombre.strip():
                st.error("Los campos 'Placa' y 'Nombre del Equipo' son obligatorios.")
            else:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                    INSERT INTO equipos (
                        placa, nombre, marca, modelo, serie, registro_invima,
                        clasificacion_riesgo, sede, ubicacion, estado,
                        fecha_ultimo_mantenimiento, fecha_proximo_mantenimiento, observaciones
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        placa.strip().upper(), nombre.strip().upper(), marca.strip().upper(),
                        modelo.strip().upper(), serie.strip().upper(), invima.strip().upper(),
                        riesgo, sede, ubicacion.strip().upper(), estado,
                        ult_mant.strftime('%Y-%m-%d'), prox_mant.strftime('%Y-%m-%d'), observaciones.strip()
                    ))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ Equipo '{nombre.upper()}' (Placa: {placa.upper()}) registrado correctamente.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Ya existe un equipo registrado con la placa '{placa.strip().upper()}'.")
                except Exception as e:
                    st.error(f"Error al registrar: {e}")

# ----------------------------------------------------
# PESTAÑA 3: ACTUALIZACIÓN Y MANTENIMIENTO
# ----------------------------------------------------
with tab_mantenimiento:
    st.subheader("Control de Mantenimientos y Actualización de Estado")
    if df_equipos.empty:
        st.info("No hay equipos registrados para actualizar.")
    else:
        col_id = 'id' if 'id' in df_equipos.columns else df_equipos.columns[0]
        col_p = [c for c in df_equipos.columns if 'PLACA' in c.upper()]
        col_n = [c for c in df_equipos.columns if 'NOMBRE' in c.upper()]

        # Genera lista de selección
        opciones_equipos = {}
        for _, row in df_equipos.iterrows():
            id_val = row[col_id]
            p_val = row[col_p[0]] if col_p else f"ID {id_val}"
            n_val = row[col_n[0]] if col_n else "Equipo"
            opciones_equipos[f"{p_val} - {n_val}"] = id_val

        seleccionado = st.selectbox("Selecciona el equipo a actualizar:", list(opciones_equipos.keys()))
        id_sel = opciones_equipos[seleccionado]

        equipo_actual = df_equipos[df_equipos[col_id] == id_sel].iloc[0]

        with st.form("form_actualizar_mantenimiento"):
            u1, u2, u3 = st.columns(3)
            with u1:
                nuevo_estado = st.selectbox(
                    "Estado Actual:",
                    ["Operativo", "En Mantenimiento", "Fuera de Servicio", "Baja"],
                    index=["Operativo", "En Mantenimiento", "Fuera de Servicio", "Baja"].index(equipo_actual.get('estado', 'Operativo')) if equipo_actual.get('estado') in ["Operativo", "En Mantenimiento", "Fuera de Servicio", "Baja"] else 0
                )
            with u2:
                n_ult_mant = st.date_input("Fecha Mantenimiento Realizado", value=date.today())
            with u3:
                n_prox_mant = st.date_input("Nueva Fecha Próximo Mantenimiento", value=date.today())

            n_obs = st.text_area("Detalles del Mantenimiento / Actividad Realizada", value=str(equipo_actual.get('observaciones', '')))

            btn_actualizar = st.form_submit_button("🔄 Actualizar Registro de Mantenimiento", type="primary")

            if btn_actualizar:
                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                    UPDATE equipos SET
                        estado = ?,
                        fecha_ultimo_mantenimiento = ?,
                        fecha_proximo_mantenimiento = ?,
                        observaciones = ?
                    WHERE id = ?
                    ''', (
                        nuevo_estado,
                        n_ult_mant.strftime('%Y-%m-%d'),
                        n_prox_mant.strftime('%Y-%m-%d'),
                        n_obs.strip(),
                        id_sel
                    ))
                    conn.commit()
                    conn.close()
                    st.success("✅ Registro actualizado correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error actualizando el registro: {e}")

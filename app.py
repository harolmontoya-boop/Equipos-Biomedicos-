import os
import io
import re
import json
import base64
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from xhtml2pdf import pisa

# Directorios base del proyecto
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "archivos_biomedicos"
STORAGE_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "biomedico.db"

app = FastAPI(title="Sistema de Control Biomédico - ASAD IPS")

# Servir archivos generados (PDFs, certificados, fotos)
app.mount("/archivos", StaticFiles(directory=str(STORAGE_DIR)), name="archivos")

# ==============================================================================
# BASE DE DATOS LOCAL (SQLite - No requiere configuración adicional)
# ==============================================================================
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    with get_db() as conn:
        cursor = conn.cursor()
        # 1. Tabla de Inventario Biomédico
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS equipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                marca TEXT, modelo TEXT, serie TEXT,
                invima TEXT, riesgo TEXT, tecnologia TEXT,
                sede TEXT, servicio TEXT, responsable TEXT,
                propiedad TEXT, frecuencia TEXT, ultimoMto TEXT,
                proximoMto TEXT, requiereCalib TEXT, proximaCalib TEXT,
                estadoOp TEXT, fechaCompra TEXT, numFactura TEXT,
                garantia TEXT, costo TEXT, proveedorNombre TEXT,
                proveedorTel TEXT, proveedorCiudad TEXT, proveedorEmail TEXT,
                voltaje TEXT, amperaje TEXT, potencia TEXT,
                frecuenciaHz TEXT, tempTrabajo TEXT, clasifUso TEXT,
                clasifBiomedica TEXT, accesoriosStr TEXT, recomendaciones TEXT,
                tipoUsuario TEXT, fotoDataUri TEXT, pdfUrlHV TEXT
            )
        """)
        # 2. Historial de Mantenimientos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mantenimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket TEXT NOT NULL,
                fecha TEXT NOT NULL,
                codigo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                serie TEXT,
                ubicacion TEXT,
                tipoServicio TEXT,
                tipoSolicitud TEXT,
                descripcionFalla TEXT,
                actividadRealizada TEXT,
                cumpleParametros TEXT,
                requirioRepuestos TEXT,
                repuestos TEXT,
                sugiereBaja TEXT,
                tecnico TEXT,
                recibe TEXT,
                supervisa TEXT,
                pdfUrl TEXT
            )
        """)
        # 3. Historial de Calibraciones
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calibraciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fechaRegistro TEXT NOT NULL,
                codigo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                sede TEXT,
                fechaVigencia TEXT,
                url TEXT
            )
        """)
        # 4. Histórico de Bajas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bajas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fechaBaja TEXT NOT NULL,
                codigo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                marca TEXT, modelo TEXT, serie TEXT,
                sede TEXT, servicio TEXT,
                motivo TEXT, destino TEXT,
                autorizadoPor TEXT, urlActa TEXT
            )
        """)
        conn.commit()

inicializar_bd()

# ==============================================================================
# FUNCIONES AUXILIARES Y MANEJO DE ARCHIVOS
# ==============================================================================
def sanitizar_nombre(nombre: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', '_', str(nombre)).strip()

def obtener_carpetas_equipo(codigo: str, nombre: str):
    cod_limpio = sanitizar_nombre(codigo)
    nom_limpio = sanitizar_nombre(nombre)
    raiz_equipo = STORAGE_DIR / f"{cod_limpio} - {nom_limpio}"
    sub_mto = raiz_equipo / "Mantenimientos"
    sub_calib = raiz_equipo / "Calibracion"
    sub_anexos = raiz_equipo / "Anexos"

    raiz_equipo.mkdir(parents=True, exist_ok=True)
    sub_mto.mkdir(parents=True, exist_ok=True)
    sub_calib.mkdir(parents=True, exist_ok=True)
    sub_anexos.mkdir(parents=True, exist_ok=True)

    return {
        "raiz": raiz_equipo,
        "mto": sub_mto,
        "calib": sub_calib,
        "anexos": sub_anexos,
        "rel_raiz": f"/archivos/{raiz_equipo.name}",
        "rel_mto": f"/archivos/{raiz_equipo.name}/Mantenimientos",
        "rel_calib": f"/archivos/{raiz_equipo.name}/Calibracion",
        "rel_anexos": f"/archivos/{raiz_equipo.name}/Anexos"
    }

def guardar_base64_archivo(base64_str: str, ruta_destino: Path):
    if "," in base64_str:
        base64_str = base64_str.split(",")[1]
    datos_binarios = base64.b64decode(base64_str)
    with open(ruta_destino, "wb") as f:
        f.write(datos_binarios)

def html_a_pdf(html_str: str, ruta_salida: Path):
    with open(ruta_salida, "wb") as f:
        pisa_status = pisa.CreatePDF(html_str, dest=f)
    return not pisa_status.err

# ==============================================================================
# GENERACIÓN DE PDF: HOJA DE VIDA (RF-EB-FR-001)
# ==============================================================================
def generar_hoja_vida_pdf(eq: dict, carpeta_equipo: Path) -> str:
    cod = sanitizar_nombre(eq.get("codigo", "EQUIPO"))
    nom = sanitizar_nombre(eq.get("nombre", "BIOMEDICO"))
    nombre_pdf = f"Hoja_De_Vida_{cod}_{nom}.pdf"
    ruta_pdf = carpeta_equipo / nombre_pdf

    # Limpiar hojas de vida viejas
    for f in carpeta_equipo.glob("Hoja_De_Vida_*.pdf"):
        try: f.unlink()
        except: pass

    # Marcas X
    fa = str(eq.get("propiedad", "")).lower()
    fa_compra = "X" if "compra" in fa or "propio" in fa else ""
    fa_comodato = "X" if "comodato" in fa else ""
    fa_donacion = "X" if "donaci" in fa else ""
    fa_otro = "X" if ("otro" in fa or not (fa_compra or fa_comodato or fa_donacion)) else ""

    freq = str(eq.get("frecuencia", "")).lower()
    f_men = "X" if "mensual" in freq and "bi" not in freq else ""
    f_bim = "X" if "bimestral" in freq else ""
    f_tri = "X" if "trimestral" in freq else ""
    f_cua = "X" if "cuatrimestral" in freq else ""
    f_sem = "X" if "semestral" in freq else ""
    f_anu = "X" if "anual" in freq else ""

    r = str(eq.get("riesgo", "")).upper()
    r_i = "X" if ("CLASE I" in r or r == "I" or "RIESGO I" in r) and "II" not in r and "III" not in r else ""
    r_iia = "X" if "IIA" in r or "II A" in r else ""
    r_iib = "X" if "IIB" in r or "II B" in r else ""
    r_iii = "X" if "III" in r else ""

    uso = str(eq.get("clasifUso", "")).lower()
    u_med = "X" if "médico" in uso or "medico" in uso else ""
    u_bas = "X" if "básico" in uso or "basico" in uso else ""
    u_apo = "X" if "apoyo" in uso else ""
    u_otr = "X" if "otro" in uso or not (u_med or u_bas or u_apo) else ""

    cb = str(eq.get("clasifBiomedica", "")).lower()
    cb_diag = "X" if "diagn" in cb else ""
    cb_vida = "X" if "vida" in cb or "mtto" in cb else ""
    cb_prev = "X" if "prev" in cb else ""
    cb_reha = "X" if "rehab" in cb else ""
    cb_lab = "X" if "lab" in cb or "odon" in cb else ""

    tec = str(eq.get("tecnologia", "")).lower()
    t_elec = "X" if "eléctrico" in tec and "electrónico" not in tec else ""
    t_elecn = "X" if "electrónico" in tec else ""
    t_elecm = "X" if "electromecánico" in tec or "electromédico" in tec else ""
    t_mec = "X" if "mecánico" in tec and "electromecánico" not in tec else ""
    t_hid = "X" if "hidráulico" in tec else ""
    t_neu = "X" if "neumático" in tec else ""
    t_acu = "X" if "acústico" in tec else ""
    t_sol = "X" if "solar" in tec else ""
    t_vap = "X" if "vapor" in tec else ""
    t_otr = "X" if "otro" in tec else ""

    calib_req = str(eq.get("requiereCalib", "NO")).upper()
    calib_str = f"SÍ (Vence: {eq.get('proximaCalib','Programada')})" if "SÍ" in calib_req or "SI" in calib_req else "NO REQUIERE"

    acc_rows = ""
    acc_list = eq.get("accesorios", [])
    if not acc_list and eq.get("accesoriosStr"):
        for item in str(eq["accesoriosStr"]).split(";"):
            item = item.strip()
            if item:
                m = re.match(r"^(\d+)\s*(.*)$", item)
                acc_list.append({"cant": m.group(1), "nombre": m.group(2)} if m else {"cant": "1", "nombre": item})

    for idx in range(5):
        if idx < len(acc_list) and acc_list[idx].get("nombre"):
            acc_rows += f"<tr><td style='text-align:center;'>{acc_list[idx].get('cant','1')}</td><td>{acc_list[idx].get('nombre','')}</td></tr>"
        else:
            acc_rows += "<tr><td style='text-align:center; height:14px;'></td><td></td></tr>"

    foto_html = f"<img src='{eq['fotoDataUri']}' style='max-width:180px; max-height:110px; object-fit:contain;'>" if eq.get("fotoDataUri") else "<div style='padding:30px; font-style:italic; color:#94a3b8;'>Sin Registro Fotográfico</div>"

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
        @page {{ size: letter portrait; margin: 10mm; }}
        body {{ font-family: Helvetica, Arial, sans-serif; font-size: 8px; color: #111; line-height: 1.15; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 4px; }}
        td, th {{ border: 1px solid #000; padding: 2.5px 4px; vertical-align: middle; }}
        .bg-header {{ background-color: #f1f5f9; font-weight: bold; }}
        .bg-title {{ background-color: #e2e8f0; font-weight: bold; text-align: center; font-size: 8.5px; }}
        .c {{ text-align: center; }} .b {{ font-weight: bold; }}
    </style></head><body>
        <table>
            <tr>
                <td rowspan="3" style="width: 22%; text-align: center; font-weight: bold; font-size: 13px;">ASAD IPS</td>
                <td class="c b" style="font-size: 10px;">PROCESO: GESTIÓN DE RECURSOS FÍSICOS Y LOGÍSTICA</td>
                <td style="width: 25%; font-size: 8px;"><strong>Código:</strong> RF-EB-FR-001</td>
            </tr>
            <tr>
                <td class="c b" style="font-size: 10.5px;">HOJA DE VIDA DE EQUIPOS BIOMÉDICOS</td>
                <td style="font-size: 8px;"><strong>Versión:</strong> 2</td>
            </tr>
            <tr>
                <td class="c" style="font-size: 7.5px;">REGISTRO TÉCNICO INSTITUCIONAL</td>
                <td style="font-size: 8px;"><strong>Fecha:</strong> 09/03/22 | Pág. 1 de 1</td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td colspan="4">IDENTIFICACIÓN INSTITUCIONAL</td></tr>
            <tr>
                <td class="bg-header" style="width: 18%;">INSTITUCIÓN:</td><td style="width: 52%;">ASISTENCIA EN SALUD DOMICILIARIA (ASAD IPS S.A.S.)</td>
                <td class="bg-header" style="width: 10%;">NIT:</td><td style="width: 20%;">900603116 - 9</td>
            </tr>
            <tr>
                <td class="bg-header">DIRECCIÓN:</td><td>CRA 4H N° 38 - 14 B/ MAGISTERIO - IBAGUE</td>
                <td class="bg-header">SEDE:</td><td><strong>{eq.get('sede','Sede Ibagué')}</strong></td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td colspan="4">INFORMACIÓN DEL EQUIPO</td></tr>
            <tr>
                <td class="bg-header" style="width: 18%;">EQUIPO:</td><td style="width: 32%;"><strong>{eq.get('nombre','')}</strong></td>
                <td class="bg-header" style="width: 18%;">MODELO:</td><td style="width: 32%;">{eq.get('modelo','N/A')}</td>
            </tr>
            <tr>
                <td class="bg-header">MARCA:</td><td>{eq.get('marca','N/A')}</td>
                <td class="bg-header">SERIE:</td><td>{eq.get('serie','NO TIENE')}</td>
            </tr>
            <tr>
                <td class="bg-header">No. REGISTRO INVIMA:</td><td>{eq.get('invima','NO TIENE')}</td>
                <td class="bg-header">CÓDIGO ACTIVO:</td><td><strong>{eq.get('codigo','')}</strong></td>
            </tr>
            <tr>
                <td class="bg-header">TIPO DE USUARIO:</td><td><strong>{eq.get('tipoUsuario','Paciente')}</strong></td>
                <td class="bg-header">CALIBRACIÓN:</td><td><strong>{calib_str}</strong></td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td colspan="2" style="width: 24%;">FORMA DE ADQUISICIÓN</td><td colspan="4" style="width: 76%;">REGISTRO HISTÓRICO Y PROVEEDOR</td></tr>
            <tr>
                <td style="width: 18%;">Compra</td><td class="c b" style="width: 6%;">{fa_compra}</td>
                <td class="bg-header" style="width: 17%;">FECHA DE COMPRA:</td><td style="width: 21%;">{eq.get('fechaCompra','N/A')}</td>
                <td class="bg-header" style="width: 16%;">No. FACTURA:</td><td style="width: 22%;">{eq.get('numFactura','N/A')}</td>
            </tr>
            <tr>
                <td>Comodato</td><td class="c b">{fa_comodato}</td>
                <td class="bg-header">GARANTÍA:</td><td>{eq.get('garantia','N/A')}</td>
                <td class="bg-header">COSTO:</td><td>{eq.get('costo','N/A')}</td>
            </tr>
            <tr>
                <td>Donación</td><td class="c b">{fa_donacion}</td>
                <td class="bg-header">PROVEEDOR:</td><td>{eq.get('proveedorNombre','N/A')}</td>
                <td class="bg-header">TELÉFONO:</td><td>{eq.get('proveedorTel','N/A')}</td>
            </tr>
            <tr>
                <td>Otro</td><td class="c b">{fa_otro}</td>
                <td class="bg-header">CIUDAD:</td><td>{eq.get('proveedorCiudad','N/A')}</td>
                <td class="bg-header">E-MAIL:</td><td>{eq.get('proveedorEmail','N/A')}</td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td colspan="12">FRECUENCIA DE MANTENIMIENTO PREVENTIVO</td></tr>
            <tr>
                <td style="width: 11.6%; text-align: right;">Mensual</td><td class="c b" style="width: 5%;">{f_men}</td>
                <td style="width: 11.6%; text-align: right;">Bimestral</td><td class="c b" style="width: 5%;">{f_bim}</td>
                <td style="width: 11.6%; text-align: right;">Trimestral</td><td class="c b" style="width: 5%;">{f_tri}</td>
                <td style="width: 11.6%; text-align: right;">Cuatrimestral</td><td class="c b" style="width: 5%;">{f_cua}</td>
                <td style="width: 11.6%; text-align: right;">Semestral</td><td class="c b" style="width: 5%;">{f_sem}</td>
                <td style="width: 11.6%; text-align: right;">Anual</td><td class="c b" style="width: 5%;">{f_anu}</td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td style="width: 44%;">REGISTRO FOTOGRÁFICO</td><td style="width: 56%;" colspan="2">ACCESORIOS PRINCIPALES</td></tr>
            <tr>
                <td rowspan="6" class="c" style="vertical-align: middle; height: 110px;">{foto_html}</td>
                <th style="width: 15%;" class="bg-header c">CANTIDAD</th>
                <th style="width: 41%;" class="bg-header c">ACCESORIO</th>
            </tr>
            {acc_rows}
        </table>

        <table>
            <tr class="bg-title"><td colspan="5">CARACTERÍSTICAS TÉCNICAS</td></tr>
            <tr>
                <td class="bg-header c">VOLTAJE</td><td class="bg-header c">AMPERAJE</td>
                <td class="bg-header c">POTENCIA</td><td class="bg-header c">FRECUENCIA</td><td class="bg-header c">TEMP. TRABAJO</td>
            </tr>
            <tr>
                <td class="c">{eq.get('voltaje','110 - 120 V')}</td><td class="c">{eq.get('amperaje','N/A')}</td>
                <td class="c">{eq.get('potencia','N/A')}</td><td class="c">{eq.get('frecuenciaHz','60 Hz')}</td>
                <td class="c">{eq.get('tempTrabajo','10°C - 40°C')}</td>
            </tr>
        </table>

        <table>
            <tr class="bg-header c" style="font-size: 7px;">
                <td colspan="2" style="width: 22%;">CLASIFICACIÓN DE RIESGO</td>
                <td colspan="2" style="width: 20%;">CLASIFICACIÓN DE USO</td>
                <td colspan="2" style="width: 26%;">CLASIFICACIÓN BIOMÉDICA</td>
                <td colspan="4" style="width: 32%;">TECNOLOGÍA PREDOMINANTE</td>
            </tr>
            <tr>
                <td style="width: 17%;">Riesgo I</td><td class="c b" style="width: 5%;">{r_i}</td>
                <td style="width: 15%;">Médico</td><td class="c b" style="width: 5%;">{u_med}</td>
                <td style="width: 21%;">Diagnóstico</td><td class="c b" style="width: 5%;">{cb_diag}</td>
                <td style="width: 11%;">Eléctrico</td><td class="c b" style="width: 5%;">{t_elec}</td>
                <td style="width: 11%;">Neumático</td><td class="c b" style="width: 5%;">{t_neu}</td>
            </tr>
            <tr>
                <td>Riesgo IIA</td><td class="c b">{r_iia}</td>
                <td>Básico</td><td class="c b">{u_bas}</td>
                <td>Mtto de la vida</td><td class="c b">{cb_vida}</td>
                <td>Electrónico</td><td class="c b">{t_elecn}</td>
                <td>Acústico</td><td class="c b">{t_acu}</td>
            </tr>
            <tr>
                <td>Riesgo IIB</td><td class="c b">{r_iib}</td>
                <td>Apoyo</td><td class="c b">{u_apo}</td>
                <td>Prevención</td><td class="c b">{cb_prev}</td>
                <td>Electromecánico</td><td class="c b">{t_elecm}</td>
                <td>Solar</td><td class="c b">{t_sol}</td>
            </tr>
            <tr>
                <td>Riesgo III</td><td class="c b">{r_iii}</td>
                <td>Otro</td><td class="c b">{u_otr}</td>
                <td>Rehabilitación</td><td class="c b">{cb_reha}</td>
                <td>Mecánico</td><td class="c b">{t_mec}</td>
                <td>Vapor</td><td class="c b">{t_vap}</td>
            </tr>
        </table>

        <table>
            <tr class="bg-title"><td>RECOMENDACIONES DEL FABRICANTE Y OBSERVACIONES</td></tr>
            <tr><td style="height: 38px; vertical-align: top;">{eq.get('recomendaciones','Operar con estabilizador de voltaje o toma regulada. Realizar limpieza y desinfección adecuada después de cada uso clínico.')}</td></tr>
        </table>
    </body></html>"""

    html_a_pdf(html, ruta_pdf)
    return f"/archivos/{carpeta_equipo.name}/{nombre_pdf}"

# ==============================================================================
# GENERACIÓN DE PDF: REPORTES DE MANTENIMIENTO PREVENTIVO Y CORRECTIVO
# ==============================================================================
def generar_reporte_mto_pdf(data: dict, carpeta_mto: Path) -> tuple:
    es_prev = data.get("tipoMantenimiento") == "PREVENTIVO"
    prefijo = "P" if es_prev else "C"
    cod = sanitizar_nombre(data.get("codigo", "EQ"))
    fecha = data.get("fechaAtencion", datetime.now().strftime("%Y-%m-%d"))

    # Contar correlativo
    archivos_previos = list(carpeta_mto.glob(f"{cod}_{prefijo}*"))
    correlativo = f"{prefijo}{len(archivos_previos) + 1}"
    ticket = data.get("ticket") or f"{cod}-{correlativo}"
    nombre_pdf = f"{cod}_{correlativo}_{fecha}.pdf"
    ruta_pdf = carpeta_mto / nombre_pdf

    ubicacion = data.get("servicio", "Domicilio Paciente")

    if es_prev:
        check = data.get("checklist", {})
        def m(k, opt):
            v = check.get(k)
            if v: return "X" if v == opt else ""
            return "X" if opt == "NA" else ""

        req_rep = data.get("requirioRepuestos") in ["SI", "SÍ"]
        sug_baj = data.get("sugiereBaja") in ["SI", "SÍ"]

        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
            @page {{ size: letter portrait; margin: 8mm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; font-size: 7.5px; color: #000; line-height: 1.15; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 3px; }}
            td, th {{ border: 1px solid #000; padding: 2px 3px; vertical-align: middle; }}
            .hdr {{ background: #f1f5f9; font-weight: bold; text-align: center; }}
            .tit {{ background: #e2e8f0; font-weight: bold; text-align: center; font-size: 8px; }}
            .c {{ text-align: center; }} .b {{ font-weight: bold; }}
            .box {{ display: inline-block; width: 8.5px; height: 8.5px; border: 1px solid #000; text-align: center; font-weight: bold; font-size: 7px; }}
        </style></head><body>
            <table>
                <tr>
                    <td rowspan="2" style="width: 22%; text-align: center; font-weight: bold; font-size: 13px;">ASAD IPS</td>
                    <td class="c b" style="font-size: 10px;">REPORTE DE MANTENIMIENTO PREVENTIVO BIOMÉDICO</td>
                    <td style="width: 25%;"><strong>No. REPORTE:</strong><br><strong style="color: #0284c7; font-size: 9.5px;">{ticket}</strong></td>
                </tr>
                <tr>
                    <td class="c b" style="font-size: 8px;">PROCESO: GESTIÓN DE RECURSOS FÍSICOS Y LOGÍSTICA</td>
                    <td><strong>FECHA REALIZADO:</strong> {fecha}</td>
                </tr>
            </table>

            <table>
                <tr><td class="hdr b" style="width: 14%;">UBICACIÓN:</td><td colspan="3">{ubicacion}</td></tr>
                <tr style="background: #eff6ff;">
                    <td class="hdr b">FECHA REALIZACIÓN:</td><td class="b" style="color: #0284c7;">{fecha}</td>
                    <td class="hdr b">PRÓXIMO MTO:</td><td class="b" style="color: #15803d;">{data.get('proxFecha', 'Según Cronograma')}</td>
                </tr>
            </table>

            <table>
                <tr class="tit"><td colspan="4">INFORMACIÓN DEL EQUIPO</td></tr>
                <tr>
                    <td class="hdr b" style="width: 14%;">EQUIPO:</td><td><strong>{data.get('nombre','')}</strong></td>
                    <td class="hdr b" style="width: 14%;">MODELO:</td><td>{data.get('modelo','N/A')}</td>
                </tr>
                <tr>
                    <td class="hdr b">MARCA:</td><td>{data.get('marca','N/A')}</td>
                    <td class="hdr b">SERIE:</td><td>{data.get('serie','NO TIENE')}</td>
                </tr>
            </table>

            <table>
                <tr class="tit"><td colspan="10">ACTIVIDADES DE MANTENIMIENTO TÉCNICO (TODOS LOS ÍTEMS EVALUADOS)</td></tr>
                <tr class="hdr">
                    <td colspan="5" style="width: 50%;">1. CONDICIONES AMBIENTALES</td>
                    <td colspan="5" style="width: 50%;">3. SEGURIDAD ELÉCTRICA</td>
                </tr>
                <tr style="font-size: 6.8px; background: #f8fafc;" class="c b">
                    <td style="width: 5%;">No</td><td style="width: 27%;">ACTIVIDAD</td><td style="width: 6%;">PASA</td><td style="width: 6%;">FALLA</td><td style="width: 6%;">N/A</td>
                    <td style="width: 5%;">No</td><td style="width: 27%;">ACTIVIDAD</td><td style="width: 6%;">PASA</td><td style="width: 6%;">FALLA</td><td style="width: 6%;">N/A</td>
                </tr>
                <tr><td class="c">1.1</td><td>HUMEDAD</td><td class="c b">{m('1.1','PASA')}</td><td class="c b">{m('1.1','FALLA')}</td><td class="c b">{m('1.1','NA')}</td><td class="c">3.1</td><td>FUGAS DE CORRIENTE</td><td class="c b">{m('3.1','PASA')}</td><td class="c b">{m('3.1','FALLA')}</td><td class="c b">{m('3.1','NA')}</td></tr>
                <tr><td class="c">1.2</td><td>POLVO</td><td class="c b">{m('1.2','PASA')}</td><td class="c b">{m('1.2','FALLA')}</td><td class="c b">{m('1.2','NA')}</td><td class="c">3.2</td><td>FUENTE DE PODER</td><td class="c b">{m('3.2','PASA')}</td><td class="c b">{m('3.2','FALLA')}</td><td class="c b">{m('3.2','NA')}</td></tr>
                <tr><td class="c">1.3</td><td>SEGURIDAD INSTALACIÓN</td><td class="c b">{m('1.3','PASA')}</td><td class="c b">{m('1.3','FALLA')}</td><td class="c b">{m('1.3','NA')}</td><td class="c">3.3</td><td>POLO A TIERRA</td><td class="c b">{m('3.3','PASA')}</td><td class="c b">{m('3.3','FALLA')}</td><td class="c b">{m('3.3','NA')}</td></tr>
                <tr><td class="c">1.4</td><td>TEMPERATURA</td><td class="c b">{m('1.4','PASA')}</td><td class="c b">{m('1.4','FALLA')}</td><td class="c b">{m('1.4','NA')}</td><td class="c">3.4</td><td>VOLTAJE FUNCIONAMIENTO</td><td class="c b">{m('3.4','PASA')}</td><td class="c b">{m('3.4','FALLA')}</td><td class="c b">{m('3.4','NA')}</td></tr>
                <tr class="hdr"><td colspan="5">2. LIMPIEZA E INSPECCIÓN INTERNA Y EXTERNA</td><td colspan="5">4. LUBRICACIÓN Y ENGRASE</td></tr>
                <tr style="font-size: 6.8px; background: #f8fafc;" class="c b">
                    <td>No</td><td>ACTIVIDAD</td><td>PASA</td><td>FALLA</td><td>N/A</td>
                    <td>No</td><td>ACTIVIDAD</td><td>PASA</td><td>FALLA</td><td>N/A</td>
                </tr>
                <tr><td class="c">2.1</td><td>ACCESORIOS</td><td class="c b">{m('2.1','PASA')}</td><td class="c b">{m('2.1','FALLA')}</td><td class="c b">{m('2.1','NA')}</td><td class="c">4.1</td><td>MOTOR</td><td class="c b">{m('4.1','PASA')}</td><td class="c b">{m('4.1','FALLA')}</td><td class="c b">{m('4.1','NA')}</td></tr>
                <tr><td class="c">2.2</td><td>ACOPLES</td><td class="c b">{m('2.2','PASA')}</td><td class="c b">{m('2.2','FALLA')}</td><td class="c b">{m('2.2','NA')}</td><td class="c">4.2</td><td>RODAMIENTOS</td><td class="c b">{m('4.2','PASA')}</td><td class="c b">{m('4.2','FALLA')}</td><td class="c b">{m('4.2','NA')}</td></tr>
                <tr><td class="c">2.3</td><td>BATERÍA</td><td class="c b">{m('2.3','PASA')}</td><td class="c b">{m('2.3','FALLA')}</td><td class="c b">{m('2.3','NA')}</td><td colspan="5" class="hdr">5. PRUEBAS DE FUNCIONAMIENTO</td></tr>
                <tr><td class="c">2.4</td><td>CABLES DE PODER</td><td class="c b">{m('2.4','PASA')}</td><td class="c b">{m('2.4','FALLA')}</td><td class="c b">{m('2.4','NA')}</td><td class="c">5.1</td><td>ALARMA SONORA</td><td class="c b">{m('5.1','PASA')}</td><td class="c b">{m('5.1','FALLA')}</td><td class="c b">{m('5.1','NA')}</td></tr>
                <tr><td class="c">2.5</td><td>VÁLVULAS</td><td class="c b">{m('2.5','PASA')}</td><td class="c b">{m('2.5','FALLA')}</td><td class="c b">{m('2.5','NA')}</td><td class="c">5.2</td><td>ALARMA VISUAL</td><td class="c b">{m('5.2','PASA')}</td><td class="c b">{m('5.2','FALLA')}</td><td class="c b">{m('5.2','NA')}</td></tr>
                <tr><td class="c">2.6</td><td>CARCASA</td><td class="c b">{m('2.6','PASA')}</td><td class="c b">{m('2.6','FALLA')}</td><td class="c b">{m('2.6','NA')}</td><td class="c">5.3</td><td>BATERÍA / AUTONOMÍA</td><td class="c b">{m('5.3','PASA')}</td><td class="c b">{m('5.3','FALLA')}</td><td class="c b">{m('5.3','NA')}</td></tr>
                <tr><td class="c">2.7</td><td>COMP. ELÉCTRICOS</td><td class="c b">{m('2.7','PASA')}</td><td class="c b">{m('2.7','FALLA')}</td><td class="c b">{m('2.7','NA')}</td><td class="c">5.4</td><td>BOTONES / TECLADO</td><td class="c b">{m('5.4','PASA')}</td><td class="c b">{m('5.4','FALLA')}</td><td class="c b">{m('5.4','NA')}</td></tr>
                <tr><td class="c">2.8</td><td>COMP. ELECTRÓNICOS</td><td class="c b">{m('2.8','PASA')}</td><td class="c b">{m('2.8','FALLA')}</td><td class="c b">{m('2.8','NA')}</td><td class="c">5.5</td><td>CABLE DE PODER</td><td class="c b">{m('5.5','PASA')}</td><td class="c b">{m('5.5','FALLA')}</td><td class="c b">{m('5.5','NA')}</td></tr>
                <tr><td class="c">2.9</td><td>COMP. MECÁNICOS</td><td class="c b">{m('2.9','PASA')}</td><td class="c b">{m('2.9','FALLA')}</td><td class="c b">{m('2.9','NA')}</td><td class="c">5.6</td><td>PANTALLA / DISPLAYS</td><td class="c b">{m('5.6','PASA')}</td><td class="c b">{m('5.6','FALLA')}</td><td class="c b">{m('5.6','NA')}</td></tr>
                <tr><td class="c">2.10</td><td>CONECTORES</td><td class="c b">{m('2.10','PASA')}</td><td class="c b">{m('2.10','FALLA')}</td><td class="c b">{m('2.10','NA')}</td><td class="c">5.7</td><td>RUEDAS Y FRENOS</td><td class="c b">{m('5.7','PASA')}</td><td class="c b">{m('5.7','FALLA')}</td><td class="c b">{m('5.7','NA')}</td></tr>
                <tr><td class="c">2.11</td><td>MANGUERAS</td><td class="c b">{m('2.11','PASA')}</td><td class="c b">{m('2.11','FALLA')}</td><td class="c b">{m('2.11','NA')}</td><td class="c">5.8</td><td>FUNCIONAMIENTO GENERAL</td><td class="c b">{m('5.8','PASA')}</td><td class="c b">{m('5.8','FALLA')}</td><td class="c b">{m('5.8','NA')}</td></tr>
                <tr><td class="c">2.12</td><td>TARJETAS ELECTRÓNICAS</td><td class="c b">{m('2.12','PASA')}</td><td class="c b">{m('2.12','FALLA')}</td><td class="c b">{m('2.12','NA')}</td><td colspan="5" style="background:#f1f5f9; text-align:center; font-size:6.8px; color:#475569;">ASAD IPS S.A.S. - PROTOCOLO BIOMÉDICO</td></tr>
            </table>

            <table>
                <tr>
                    <td class="hdr b" style="width: 25%;">REQUIRIÓ REPUESTOS:</td>
                    <td style="width: 22%; text-align: center;">
                        SÍ <span class="box">{'X' if req_rep else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp;
                        NO <span class="box">{'X' if not req_rep else ''}</span>
                    </td>
                    <td class="hdr b" style="width: 18%;">REPUESTOS:</td>
                    <td style="width: 35%;">{data.get('repuestos', 'NINGUNO')}</td>
                </tr>
                <tr>
                    <td class="hdr b">SUGIERE BAJA:</td>
                    <td style="text-align: center;">
                        SÍ <span class="box">{'X' if sug_baj else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp;
                        NO <span class="box">{'X' if not sug_baj else ''}</span>
                    </td>
                    <td class="hdr b">JUSTIFICACIÓN:</td>
                    <td>{data.get('justificacionBaja', 'NINGUNA')}</td>
                </tr>
            </table>

            <table>
                <tr class="tit"><td>OBSERVACIONES DEL MANTENIMIENTO PREVENTIVO</td></tr>
                <tr><td style="height:30px; vertical-align:top;">{data.get('observaciones', 'Equipo probado y operativo bajo parámetros normativos de calidad.')}</td></tr>
            </table>

            <table style="margin-top:5px;">
                <tr>
                    <td style="width:50%; text-align:center; height:45px; vertical-align:bottom;">
                        {"<img src='" + data['firmaTecnicoImg'] + "' style='max-height:30px;'><br>" if data.get('firmaTecnicoImg') else ""}
                        <hr style="border:0.5px solid #000; width:80%; margin:2px auto;">
                        <strong style="font-size:7.5px;">FIRMA QUIEN REALIZÓ MTTO</strong><br>
                        <span style="font-size:7px;">{data.get('firmaTecnicoNombre','')}</span><br>
                        <span style="font-size:6.5px;"><strong>Fecha:</strong> {fecha}</span>
                    </td>
                    <td style="width:50%; text-align:center; height:45px; vertical-align:bottom;">
                        {"<img src='" + data['firmaRecibeImg'] + "' style='max-height:30px;'><br>" if data.get('firmaRecibeImg') else ""}
                        <hr style="border:0.5px solid #000; width:80%; margin:2px auto;">
                        <strong style="font-size:7.5px;">FIRMA QUIEN RECIBE MTTO</strong><br>
                        <span style="font-size:7px;">{data.get('firmaRecibeNombre','')}</span><br>
                        <span style="font-size:6.5px;"><strong>Fecha:</strong> {fecha}</span>
                    </td>
                </tr>
            </table>
        </body></html>"""
    else:
        c_ok = data.get("cumpleParametros") in ["SI", "SÍ"]
        r_ok = data.get("requirioRepuestos") in ["SI", "SÍ"]
        b_ok = data.get("sugiereBaja") in ["SI", "SÍ"]

        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
            @page {{ size: letter portrait; margin: 10mm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; font-size: 8.5px; color: #111; line-height: 1.2; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 5px; }}
            td, th {{ border: 1px solid #000; padding: 3px 5px; vertical-align: middle; }}
            .hdr {{ background: #f1f5f9; font-weight: bold; }}
            .c {{ text-align: center; }} .b {{ font-weight: bold; }}
            .box {{ display: inline-block; width: 9px; height: 9px; border: 1px solid #000; text-align: center; font-size: 7.5px; font-weight: bold; }}
        </style></head><body>
            <table>
                <tr>
                    <td rowspan="3" style="width: 24%; text-align: center; font-weight: bold; font-size: 14px;">ASAD IPS</td>
                    <td class="c b">PROCESO: GESTIÓN DE RECURSOS FÍSICOS Y LOGÍSTICA</td>
                    <td style="width: 25%;"><strong>Código:</strong> RF-EB-FR-005</td>
                </tr>
                <tr>
                    <td class="c b" style="font-size: 10.5px;">SOLICITUD DE REVISIÓN Y/O MANTENIMIENTO</td>
                    <td><strong>Versión:</strong> 1</td>
                </tr>
                <tr>
                    <td class="c">REGISTRO OFICIAL DE INTERVENCIÓN BIOMÉDICA</td>
                    <td><strong>Fecha Realizado:</strong> {fecha}</td>
                </tr>
            </table>

            <table>
                <tr class="hdr"><td colspan="4">MODALIDAD DE SERVICIO ATENDIDO</td></tr>
                <tr>
                    <td style="width: 25%;">Verificación Funcionamiento <span class="box">{'X' if 'Verificación' in data.get('tipoServicio','') else ''}</span></td>
                    <td style="width: 25%;">Mantenimiento Correctivo <span class="box">{'X' if 'Correctivo' in data.get('tipoServicio','') or not es_prev else ''}</span></td>
                    <td style="width: 25%;">Mantenimiento Preventivo <span class="box">{'X' if 'Preventivo' in data.get('tipoServicio','') else ''}</span></td>
                    <td style="width: 25%;">Instalación / Inducción <span class="box">{'X' if 'Instalación' in data.get('tipoServicio','') else ''}</span></td>
                </tr>
            </table>

            <table>
                <tr class="hdr"><td colspan="6">INFORMACIÓN DE LA SOLICITUD Y DATOS DEL ACTIVO</td></tr>
                <tr>
                    <td class="hdr">EQUIPO:</td><td><strong>{data.get('nombre','')}</strong></td>
                    <td class="hdr">SERIE:</td><td>{data.get('serie','NO TIENE')}</td>
                    <td class="hdr">ID:</td><td><strong>{cod}</strong></td>
                </tr>
                <tr>
                    <td class="hdr">UBICACIÓN:</td><td colspan="3">{ubicacion}</td>
                    <td class="hdr">TICKET:</td><td><strong style="color: #0284c7;">{ticket}</strong></td>
                </tr>
                <tr style="background: #eff6ff;">
                    <td class="hdr">FECHA:</td><td><strong>{fecha}</strong></td>
                    <td class="hdr">SOLICITUD:</td><td>Escrita <span class="box">{'X' if data.get('tipoSolicitud')=='ESCRITA' else ''}</span> &nbsp; Telefónica <span class="box">{'X' if data.get('tipoSolicitud')!='ESCRITA' else ''}</span></td>
                    <td class="hdr">SOLICITA:</td><td>{data.get('solicitante', 'Personal Asistencial')}</td>
                </tr>
                <tr><td class="hdr">FALLA:</td><td colspan="5">{data.get('descripcionFalla','Falla técnica reportada')}</td></tr>
            </table>

            <table>
                <tr class="hdr"><td colspan="4">ACTIVIDAD TÉCNICA REALIZADA / DIAGNÓSTICO</td></tr>
                <tr><td colspan="4" style="height: 42px; vertical-align: top;">{data.get('actividadRealizada', data.get('observaciones','Intervención técnica realizada a satisfacción.'))}</td></tr>
            </table>

            <table>
                <tr class="hdr"><td colspan="4">EVALUACIÓN TÉCNICA Y RESULTADO (TODOS LOS CRITERIOS)</td></tr>
                <tr><td colspan="3">¿El equipo funciona dentro de los parámetros establecidos?</td><td class="c">SÍ <span class="box">{'X' if c_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; NO <span class="box">{'X' if not c_ok else ''}</span></td></tr>
                <tr><td colspan="3">¿La intervención técnica solucionó integralmente la novedad?</td><td class="c">SÍ <span class="box">{'X' if c_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; NO <span class="box">{ 'X' if not c_ok else ''}</span></td></tr>
                <tr><td colspan="3">¿Requirió repuestos y/o reemplazo de partes?</td><td class="c">SÍ <span class="box">{'X' if r_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; NO <span class="box">{'X' if not r_ok else ''}</span></td></tr>
                <tr><td class="hdr">REPUESTOS:</td><td colspan="3">{data.get('repuestos', 'NINGUNO')}</td></tr>
                <tr><td colspan="3">¿Se sugiere dar de baja técnica por obsolescencia o daño irreparable?</td><td class="c">SÍ <span class="box">{'X' if b_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; NO <span class="box">{'X' if not b_ok else ''}</span></td></tr>
                <tr style="background: #eff6ff;"><td class="hdr">ESTADO FINAL:</td><td colspan="3" class="c b">Operativo <span class="box">{'X' if c_ok and not b_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; Fuera de Servicio <span class="box">{'X' if not c_ok and not b_ok else ''}</span> &nbsp;&nbsp;&nbsp;&nbsp; Pendiente de Baja <span class="box">{'X' if b_ok else ''}</span></td></tr>
            </table>

            <table style="margin-top: 8px;">
                <tr>
                    <td style="width: 33.3%; text-align: center; height: 50px; vertical-align: bottom;">
                        {"<img src='" + data['firmaTecnicoImg'] + "' style='max-height:30px;'><br>" if data.get('firmaTecnicoImg') else ""}
                        <hr style="border:0.5px solid #000; margin:2px 8px;"><strong style="font-size:7.5px;">FIRMA REALIZA MTTO</strong><br>
                        <span style="font-size:7px;">{data.get('firmaTecnicoNombre','')}</span><br><span style="font-size:6.5px;"><strong>Fecha:</strong> {fecha}</span>
                    </td>
                    <td style="width: 33.3%; text-align: center; height: 50px; vertical-align: bottom;">
                        {"<img src='" + data['firmaRecibeImg'] + "' style='max-height:30px;'><br>" if data.get('firmaRecibeImg') else ""}
                        <hr style="border:0.5px solid #000; margin:2px 8px;"><strong style="font-size:7.5px;">FIRMA RECIBE MTTO</strong><br>
                        <span style="font-size:7px;">{data.get('firmaRecibeNombre','')}</span><br><span style="font-size:6.5px;"><strong>Fecha:</strong> {fecha}</span>
                    </td>
                    <td style="width: 33.3%; text-align: center; height: 50px; vertical-align: bottom;">
                        {"<img src='" + data['firmaSupervisaImg'] + "' style='max-height:30px;'><br>" if data.get('firmaSupervisaImg') else ""}
                        <hr style="border:0.5px solid #000; margin:2px 8px;"><strong style="font-size:7.5px;">SUPERVISIÓN MTTO</strong><br>
                        <span style="font-size:7px;">{data.get('firmaSupervisaNombre','Harol Camilo Montoya')}</span><br><span style="font-size:6.5px;"><strong>Fecha:</strong> {fecha}</span>
                    </td>
                </tr>
            </table>
        </body></html>"""

    html_a_pdf(html, ruta_pdf)
    return ticket, f"/archivos/{carpeta_mto.parent.name}/Mantenimientos/{nombre_pdf}"

# ==============================================================================
# RUTAS DE LA API (Equivalentes a las funciones de Google Apps Script)
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
def index():
    ruta_html = BASE_DIR / "index.html"
    if not ruta_html.exists():
        return HTMLResponse("<h3>Coloca tu archivo index.html en la misma carpeta que app.py</h3>", status_code=200)
    with open(ruta_html, "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/obtenerEquipos")
def api_obtener_equipos():
    with get_db() as conn:
        cursor = conn.cursor()
        filas = cursor.execute("SELECT * FROM equipos ORDER BY id ASC").fetchall()
        equipos = [dict(f) for f in filas]
    return equipos

@app.post("/api/obtenerHistorialMantenimientos")
def api_obtener_historial_mantenimientos():
    with get_db() as conn:
        cursor = conn.cursor()
        filas = cursor.execute("SELECT * FROM mantenimientos ORDER BY id DESC").fetchall()
        historial = [dict(f) for f in filas]
    return historial

@app.post("/api/obtenerHistorialCalibraciones")
def api_obtener_historial_calibraciones():
    with get_db() as conn:
        cursor = conn.cursor()
        filas = cursor.execute("SELECT * FROM calibraciones ORDER BY id DESC").fetchall()
        calibs = [dict(f) for f in filas]
    return calibs

@app.post("/api/obtenerExpedienteEquipo")
def api_obtener_expediente(payload: dict):
    codigo = payload.get("codigo", "")
    nombre = payload.get("nombre", "")
    carpetas = obtener_carpetas_equipo(codigo, nombre)

    def listar_archivos(directorio: Path, rel_url: str):
        archivos = []
        for a in directorio.glob("*"):
            if a.is_file():
                archivos.append({
                    "id": a.name,
                    "nombre": a.name,
                    "url": f"{rel_url}/{a.name}",
                    "fecha": datetime.fromtimestamp(a.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "tamano": f"{a.stat().st_size / 1024:.1f} KB"
                })
        return sorted(archivos, key=lambda x: x["fecha"], reverse=True)

    url_hv = ""
    for f in carpetas["raiz"].glob("Hoja_De_Vida_*.pdf"):
        url_hv = f"{carpetas['rel_raiz']}/{f.name}"
        break

    return {
        "carpetaUrl": carpetas["rel_raiz"],
        "urlMto": carpetas["rel_mto"],
        "urlCalib": carpetas["rel_calib"],
        "urlAnexos": carpetas["rel_anexos"],
        "urlHV": url_hv,
        "archivosMto": listar_archivos(carpetas["mto"], carpetas["rel_mto"]),
        "archivosCalib": listar_archivos(carpetas["calib"], carpetas["rel_calib"]),
        "archivosAnexos": listar_archivos(carpetas["anexos"], carpetas["rel_anexos"])
    }

@app.post("/api/procesarEquipo")
def api_procesar_equipo(payload: dict):
    accion = payload.get("action")
    eq = payload.get("equipo", {})
    codigo = payload.get("codigo") or eq.get("codigo")
    fila_id = payload.get("filaId")

    carpetas = obtener_carpetas_equipo(codigo, eq.get("nombre", "Equipo"))

    with get_db() as conn:
        cursor = conn.cursor()

        if accion == "crear":
            pdf_url = generar_hoja_vida_pdf(eq, carpetas["raiz"])
            cursor.execute("""
                INSERT INTO equipos (
                    codigo, nombre, marca, modelo, serie, invima, riesgo, tecnologia,
                    sede, servicio, responsable, propiedad, frecuencia, ultimoMto, proximoMto,
                    requiereCalib, proximaCalib, estadoOp, fechaCompra, numFactura, garantia,
                    costo, proveedorNombre, proveedorTel, proveedorCiudad, proveedorEmail,
                    voltaje, amperaje, potencia, frecuenciaHz, tempTrabajo, clasifUso,
                    clasifBiomedica, accesoriosStr, recomendaciones, tipoUsuario, fotoDataUri, pdfUrlHV
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                eq.get("codigo"), eq.get("nombre"), eq.get("marca"), eq.get("modelo"), eq.get("serie","NO TIENE"),
                eq.get("invima","NO TIENE"), eq.get("riesgo","Clase IIb"), eq.get("tecnologia","Electromédico"),
                eq.get("sede","Sede Ibagué"), eq.get("servicio","Domicilio Paciente"), eq.get("responsable",""),
                eq.get("propiedad","Compra"), eq.get("frecuencia","Trimestral"), eq.get("ultimoMto",""), eq.get("proximoMto",""),
                eq.get("requiereCalib","NO"), eq.get("proximaCalib",""), eq.get("estadoOp","Operativo"),
                eq.get("fechaCompra",""), eq.get("numFactura",""), eq.get("garantia",""), eq.get("costo",""),
                eq.get("proveedorNombre",""), eq.get("proveedorTel",""), eq.get("proveedorCiudad",""), eq.get("proveedorEmail",""),
                eq.get("voltaje",""), eq.get("amperaje",""), eq.get("potencia",""), eq.get("frecuenciaHz",""), eq.get("tempTrabajo",""),
                eq.get("clasifUso","Médico"), eq.get("clasifBiomedica","Diagnóstico"), eq.get("accesoriosStr",""),
                eq.get("recomendaciones",""), eq.get("tipoUsuario","Paciente"), eq.get("fotoDataUri",""), pdf_url
            ))
            conn.commit()
            return {"status": "success", "pdfUrlHV": pdf_url}

        elif accion == "editar":
            pdf_url = generar_hoja_vida_pdf(eq, carpetas["raiz"])
            cursor.execute("""
                UPDATE equipos SET
                    nombre=?, marca=?, modelo=?, serie=?, invima=?, riesgo=?, tecnologia=?,
                    sede=?, servicio=?, responsable=?, propiedad=?, frecuencia=?, ultimoMto=?, proximoMto=?,
                    requiereCalib=?, proximaCalib=?, estadoOp=?, fechaCompra=?, numFactura=?, garantia=?,
                    costo=?, proveedorNombre=?, proveedorTel=?, proveedorCiudad=?, proveedorEmail=?,
                    voltaje=?, amperaje=?, potencia=?, frecuenciaHz=?, tempTrabajo=?, clasifUso=?,
                    clasifBiomedica=?, accesoriosStr=?, recomendaciones=?, tipoUsuario=?, pdfUrlHV=?
                WHERE codigo=?
            """, (
                eq.get("nombre"), eq.get("marca"), eq.get("modelo"), eq.get("serie"), eq.get("invima"),
                eq.get("riesgo"), eq.get("tecnologia"), eq.get("sede"), eq.get("servicio"), eq.get("responsable"),
                eq.get("propiedad"), eq.get("frecuencia"), eq.get("ultimoMto"), eq.get("proximoMto"),
                eq.get("requiereCalib"), eq.get("proximaCalib"), eq.get("estadoOp"), eq.get("fechaCompra"),
                eq.get("numFactura"), eq.get("garantia"), eq.get("costo"), eq.get("proveedorNombre"),
                eq.get("proveedorTel"), eq.get("proveedorCiudad"), eq.get("proveedorEmail"), eq.get("voltaje"),
                eq.get("amperaje"), eq.get("potencia"), eq.get("frecuenciaHz"), eq.get("tempTrabajo"),
                eq.get("clasifUso"), eq.get("clasifBiomedica"), eq.get("accesoriosStr"), eq.get("recomendaciones"),
                eq.get("tipoUsuario"), pdf_url, codigo
            ))
            conn.commit()
            return {"status": "success", "pdfUrlHV": pdf_url}

        elif accion == "eliminar":
            cursor.execute("DELETE FROM equipos WHERE codigo=?", (codigo,))
            conn.commit()
            return {"status": "success"}

@app.post("/api/registrarMantenimiento")
def api_registrar_mantenimiento(data: dict):
    codigo = data.get("codigo")
    nombre = data.get("nombre", "Equipo")
    es_prev = data.get("tipoMantenimiento") == "PREVENTIVO"

    carpetas = obtener_carpetas_equipo(codigo, nombre)

    # Calcular próxima fecha si es preventivo
    prox_fecha = ""
    fecha_atencion = data.get("fechaAtencion") or datetime.now().strftime("%Y-%m-%d")
    if es_prev and fecha_atencion:
        try:
            d = datetime.strptime(fecha_atencion, "%Y-%m-%d")
            freq = str(data.get("frecuencia", "")).lower()
            dias = 90
            if "mensual" in freq and "bi" not in freq: dias = 30
            elif "bimestral" in freq: dias = 60
            elif "semestral" in freq: dias = 180
            elif "cuatrimestral" in freq: dias = 120
            elif "anual" in freq: dias = 365
            prox_fecha = (d + timedelta(days=dias)).strftime("%Y-%m-%d")
        except: pass
    data["proxFecha"] = prox_fecha

    ticket, pdf_url = generar_reporte_mto_pdf(data, carpetas["mto"])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mantenimientos (
                ticket, fecha, codigo, nombre, serie, ubicacion, tipoServicio,
                tipoSolicitud, descripcionFalla, actividadRealizada, cumpleParametros,
                requirioRepuestos, repuestos, sugiereBaja, tecnico, recibe, supervisa, pdfUrl
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            ticket, fecha_atencion, codigo, nombre, data.get("serie",""),
            f"{data.get('sede','')} - {data.get('servicio','')}",
            "Mantenimiento Preventivo" if es_prev else data.get("tipoServicio","Mantenimiento Correctivo"),
            data.get("tipoSolicitud","PROGRAMADO"), data.get("descripcionFalla",""),
            data.get("actividadRealizada") or data.get("observaciones",""),
            data.get("cumpleParametros","SI"), data.get("requirioRepuestos","NO"),
            data.get("repuestos","NINGUNO"), data.get("sugiereBaja","NO"),
            data.get("firmaTecnicoNombre",""), data.get("firmaRecibeNombre",""),
            data.get("firmaSupervisaNombre","Harol Camilo Montoya"), pdf_url
        ))

        # Actualizar equipo
        if es_prev and prox_fecha:
            cursor.execute("UPDATE equipos SET ultimoMto=?, proximoMto=? WHERE codigo=?", (fecha_atencion, prox_fecha, codigo))
        if data.get("sugiereBaja") == "SI":
            cursor.execute("UPDATE equipos SET estadoOp='Pendiente de Baja' WHERE codigo=?", (codigo,))
        elif data.get("cumpleParametros") == "SI" or es_prev:
            cursor.execute("UPDATE equipos SET estadoOp='Operativo' WHERE codigo=?", (codigo,))

        conn.commit()

    return {"status": "success", "ticket": ticket, "pdfUrl": pdf_url}

@app.post("/api/subirCertificadoCalibracion")
def api_subir_certificado(data: dict):
    codigo = data.get("codigo")
    nombre = data.get("nombre", "Equipo")
    carpetas = obtener_carpetas_equipo(codigo, nombre)

    nombre_archivo = sanitizar_nombre(data.get("nombreArchivo", "Certificado.pdf"))
    if not nombre_archivo.endswith(".pdf"): nombre_archivo += ".pdf"
    ruta_guardado = carpetas["calib"] / nombre_archivo

    guardar_base64_archivo(data.get("base64Data", ""), ruta_guardado)
    url_archivo = f"{carpetas['rel_calib']}/{nombre_archivo}"

    hoy = datetime.now().strftime("%Y-%m-%d")
    fecha_calib = data.get("fechaCalib", "")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE equipos SET requiereCalib='SÍ', proximaCalib=? WHERE codigo=?", (fecha_calib, codigo))
        cursor.execute("""
            INSERT INTO calibraciones (fechaRegistro, codigo, nombre, sede, fechaVigencia, url)
            VALUES (?,?,?,?,?,?)
        """, (hoy, codigo, nombre, data.get("sede",""), fecha_calib, url_archivo))
        conn.commit()

    return {"status": "success", "url": url_archivo}

@app.post("/api/subirDocumentoAnexo")
def api_subir_anexo(data: dict):
    codigo = data.get("codigo")
    nombre = data.get("nombre", "Equipo")
    carpetas = obtener_carpetas_equipo(codigo, nombre)

    prefijo = (data.get("tipoAnexo", "Anexo").replace(" ", "_")) + "_"
    nombre_final = prefijo + sanitizar_nombre(data.get("nombreArchivo", "documento.pdf"))
    ruta_guardado = carpetas["anexos"] / nombre_final

    guardar_base64_archivo(data.get("base64Data", ""), ruta_guardado)
    url_archivo = f"{carpetas['rel_anexos']}/{nombre_final}"

    return {"status": "success", "url": url_archivo, "nombre": nombre_final}

@app.post("/api/formalizarBajaEquipo")
def api_formalizar_baja(data: dict):
    codigo = data.get("codigo")
    nombre = data.get("nombre", "Equipo")
    carpetas = obtener_carpetas_equipo(codigo, nombre)

    nombre_pdf = f"Acta_Baja_{sanitizar_nombre(codigo)}.pdf"
    ruta_guardado = carpetas["raiz"] / nombre_pdf
    guardar_base64_archivo(data.get("base64Pdf", ""), ruta_guardado)
    url_pdf = f"{carpetas['rel_raiz']}/{nombre_pdf}"

    hoy = datetime.now().strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO bajas (fechaBaja, codigo, nombre, marca, modelo, serie, sede, servicio, motivo, destino, autorizadoPor, urlActa)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            hoy, codigo, nombre, data.get("marca"), data.get("modelo"), data.get("serie"),
            data.get("sede"), data.get("servicio"), data.get("motivo"), data.get("destino"),
            data.get("autorizadoPor"), url_pdf
        ))
        cursor.execute("DELETE FROM equipos WHERE codigo=?", (codigo,))
        conn.commit()

    return {"status": "success"}

@app.post("/api/eliminarArchivoExpediente")
def api_eliminar_archivo(data: dict):
    file_id = data.get("fileId") # Es el nombre del archivo
    codigo = data.get("codigo")
    # Buscar en subcarpetas
    for root, dirs, files in os.walk(str(STORAGE_DIR)):
        if file_id in files:
            try:
                os.remove(os.path.join(root, file_id))
            except: pass

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mantenimientos WHERE pdfUrl LIKE ?", (f"%{file_id}%",))
        conn.commit()

    return {"status": "success"}

@app.post("/api/cargarEquiposMasivo")
def api_cargar_masivo(payload: dict):
    lista = payload.get("lista", [])
    if not lista: return {"status": "empty"}

    ins, act = 0, 0
    with get_db() as conn:
        cursor = conn.cursor()
        for eq in lista:
            cod = eq.get("codigo")
            if not cod: continue
            existe = cursor.execute("SELECT id FROM equipos WHERE codigo=?", (cod,)).fetchone()
            if existe:
                cursor.execute("""
                    UPDATE equipos SET
                        nombre=?, marca=?, modelo=?, serie=?, invima=?, sede=?, servicio=?,
                        tipoUsuario=?, responsable=?, estadoOp=?
                    WHERE codigo=?
                """, (
                    eq.get("nombre"), eq.get("marca"), eq.get("modelo"), eq.get("serie"),
                    eq.get("invima"), eq.get("sede"), eq.get("servicio"), eq.get("tipoUsuario"),
                    eq.get("responsable"), eq.get("estadoOp"), cod
                ))
                act += 1
            else:
                cursor.execute("""
                    INSERT INTO equipos (codigo, nombre, marca, modelo, serie, invima, sede, servicio, tipoUsuario, responsable, estadoOp)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    cod, eq.get("nombre"), eq.get("marca"), eq.get("modelo"), eq.get("serie"),
                    eq.get("invima"), eq.get("sede"), eq.get("servicio"), eq.get("tipoUsuario"),
                    eq.get("responsable"), eq.get("estadoOp")
                ))
                ins += 1
        conn.commit()

    return {"status": "success", "insertados": ins, "actualizados": act, "total": ins + act}

@app.post("/api/descargarCarpetasZip")
def api_descargar_zip(payload: dict):
    lista = payload.get("lista", [])
    if not lista:
        return {"status": "empty", "mensaje": "No se han seleccionado equipos."}

    zip_buffer = io.BytesIO()
    total_archivos = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in lista:
            cod = sanitizar_nombre(item.get("codigo"))
            nom = sanitizar_nombre(item.get("nombre", ""))
            carpeta = STORAGE_DIR / f"{cod} - {nom}"
            if carpeta.exists():
                for root, _, files in os.walk(carpeta):
                    for file in files:
                        full_path = Path(root) / file
                        arcname = full_path.relative_to(STORAGE_DIR)
                        zip_file.write(full_path, arcname=arcname)
                        total_archivos += 1

    if total_archivos == 0:
        return {"status": "empty", "mensaje": "Las carpetas seleccionadas no contienen archivos aún."}

    zip_bytes = zip_buffer.getvalue()
    b64_zip = base64.b64encode(zip_bytes).decode('utf-8')
    nombre_zip = f"Carpetas_Biomedicas_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"

    return {
        "status": "success",
        "nombreArchivo": nombre_zip,
        "totalArchivos": total_archivos,
        "base64": b64_zip
    }
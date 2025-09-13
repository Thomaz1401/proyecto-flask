from flask import Flask, request, render_template_string, send_file, session
import os
import pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename
import json
import unicodedata
import io

app = Flask(__name__)
app.secret_key = "mi_clave_secreta"

# Carpeta para guardar uploads (solo se guarda el archivo original que sube el usuario)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"txt", "log", "csv"}

def allowed_file(filename):
    if "." not in filename:
        return True
    return filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ✅ Limpieza de texto para acentos/caracteres especiales
def limpiar_texto(texto):
    if not isinstance(texto, str):
        return texto
    return unicodedata.normalize("NFKC", texto)

def generar_dataframe(filepath):
    """Lee el archivo y devuelve DataFrame con columnas necesarias"""
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lineas = f.readlines()

    datos = []
    for linea in lineas:
        partes = linea.strip().split("|")
        fila = {}
        for i, valor in enumerate(partes):
            fila[f"col{i}"] = limpiar_texto(valor.strip())

        # convertir col0 en fecha legible
        try:
            ts = int(partes[0])
            fila["fecha_legible"] = datetime.fromtimestamp(ts)
        except:
            fila["fecha_legible"] = None

        datos.append(fila)

    df = pd.DataFrame(datos)

    # Reordenar columnas
    if "col0" in df.columns and "fecha_legible" in df.columns:
        cols = df.columns.tolist()
        cols.remove("fecha_legible")
        insert_at = cols.index("col0") + 1
        cols.insert(insert_at, "fecha_legible")
        df = df[cols]

    # Conservar solo columnas necesarias
    columnas_finales = [c for c in ["col0", "fecha_legible", "col2", "col4", "col6"] if c in df.columns]
    df = df[columnas_finales]

    # Renombrar columnas
    df = df.rename(columns={
        "col0": "timestamp",
        "col2": "cola",
        "col4": "evento",
        "col6": "numero_telefono"
    })

    # ✅ Cargar traducciones desde eventos.json
    try:
        with open("eventos.json", "r", encoding="utf-8") as f:
            traduccion_eventos = json.load(f)
        if "evento" in df.columns:
            df["evento"] = df["evento"].replace(traduccion_eventos)
    except Exception as e:
        print(f"⚠️ No se pudo cargar eventos.json: {e}")

    return df

# ✅ Nueva versión: genera reporte en memoria
def generar_reporte_memoria(df, formato="excel"):
    output = io.BytesIO()
    if formato == "excel":
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name="Reporte", index=False)
    else:
        output.write(df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"))

    output.seek(0)
    return output

@app.route("/", methods=["GET", "POST"])
def index():
    mensaje = ""
    preview_html = "<p class='text-gray-500'>Sube un archivo para ver la vista previa aquí.</p>"

    if request.method == "POST":
        if "file" in request.files:
            file = request.files["file"]
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename) or "queue_log"
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)

                session["last_file"] = filepath
                mensaje = f"✅ Archivo <b>{filename}</b> subido con éxito."

                # Generar vista previa
                df = generar_dataframe(filepath)
                if df is not None and not df.empty:
                    preview_html = df.head(20).to_html(
                        classes="table-auto w-full border-collapse border border-blue-200 text-sm text-gray-800",
                        index=False
                    )
            else:
                mensaje = "⚠️ Tipo de archivo no permitido."

    botones_disabled = "" if session.get("last_file") else "opacity-50 pointer-events-none"

    html = f"""
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Generador de Reportes</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gradient-to-r from-blue-50 to-blue-100 min-h-screen flex items-center justify-center p-6">
        <div class="max-w-6xl w-full bg-white shadow-2xl rounded-2xl p-8">
            <h1 class="text-3xl font-bold text-blue-800 mb-4 text-center">📊 Generador de Reportes</h1>

            <p class="text-center text-green-600 mb-4">{mensaje}</p>

            <form method="POST" enctype="multipart/form-data" class="text-center mb-6">
                <input type="file" name="file" 
                       class="mb-4 block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4
                              file:rounded-lg file:border-0 file:text-sm file:font-semibold
                              file:bg-blue-600 file:text-white hover:file:bg-blue-700"/>
                <button type="submit"
                        class="bg-blue-700 hover:bg-blue-800 text-white font-semibold py-2 px-6 rounded-xl shadow-lg transition">
                    📤 Subir archivo
                </button>
            </form>

            <div class="flex justify-center gap-4 mb-8 {botones_disabled}">
                <a href="/generar/excel" 
                   class="bg-blue-700 hover:bg-blue-800 text-white font-semibold py-3 px-6 rounded-xl shadow-lg transition">
                   📥 Descargar Excel
                </a>
                <a href="/generar/csv" 
                   class="bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-xl shadow-lg transition">
                   📥 Descargar CSV
                </a>
            </div>

            <h2 class="text-xl font-semibold text-blue-700 mb-3">Vista previa (20 filas):</h2>
            <div class="overflow-x-auto rounded-lg border border-blue-200 bg-blue-50 p-2">
                {preview_html}
            </div>

            <footer class="mt-6 text-gray-400 text-sm text-center">
                © 2025 Generador de Reportes – by Thomas 💻
            </footer>
        </div>
    </body>
    </html>
    """
    return html

@app.route("/generar/<formato>")
def generar(formato):
    filepath = session.get("last_file")
    if not filepath or not os.path.exists(filepath):
        return "❌ Primero debes subir un archivo.", 400

    df = generar_dataframe(filepath)
    archivo = generar_reporte_memoria(df, formato)

    # ✅ Enviar archivo en memoria
    if formato == "excel":
        return send_file(archivo, as_attachment=True,
                         download_name="reporte.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        return send_file(archivo, as_attachment=True,
                         download_name="reporte.csv",
                         mimetype="text/csv")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

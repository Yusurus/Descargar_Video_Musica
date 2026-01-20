import os
import json
import subprocess
import sys
import threading
import queue
import time
import shutil
import uuid
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, send_file
import yt_dlp

app = Flask(__name__)

# --- CONFIGURACIÓN ---
BASE_TEMP_FOLDER = os.path.join(os.getcwd(), 'temp_downloads')
TIEMPO_EXPIRACION_MINUTOS = 10  # Los archivos se borran después de 10 minutos

# Asegurar que existe la carpeta base
if not os.path.exists(BASE_TEMP_FOLDER):
    os.makedirs(BASE_TEMP_FOLDER)

# --- SISTEMA DE LIMPIEZA AUTOMÁTICA (GARBAGE COLLECTOR) ---
def tarea_limpieza_fondo():
    """Este 'conserje' revisa carpetas viejas y las borra para liberar espacio."""
    while True:
        try:
            ahora = time.time()
            # Umbral: Tiempo actual menos X minutos (en segundos)
            limite = ahora - (TIEMPO_EXPIRACION_MINUTOS * 60)

            if os.path.exists(BASE_TEMP_FOLDER):
                for nombre_carpeta in os.listdir(BASE_TEMP_FOLDER):
                    ruta_carpeta = os.path.join(BASE_TEMP_FOLDER, nombre_carpeta)
                    
                    # Verificamos si es una carpeta
                    if os.path.isdir(ruta_carpeta):
                        # Obtenemos la fecha de modificación de la carpeta
                        fecha_modificacion = os.path.getmtime(ruta_carpeta)
                        
                        if fecha_modificacion < limite:
                            print(f"🧹 Limpiando basura antigua: {nombre_carpeta}")
                            shutil.rmtree(ruta_carpeta, ignore_errors=True)
            
            # El conserje descansa 60 segundos antes de volver a revisar
            time.sleep(60)
        except Exception as e:
            print(f"Error en limpieza: {e}")
            time.sleep(60)

# Iniciamos el hilo de limpieza apenas arranca el servidor
hilo_limpieza = threading.Thread(target=tarea_limpieza_fondo, daemon=True)
hilo_limpieza.start()

# --- UTILIDADES ---
def formatear_bytes(num_bytes):
    if num_bytes is None: return "0 B"
    for unidad in ['B', 'KiB', 'MiB', 'GiB']:
        if num_bytes < 1024.0: return f"{num_bytes:.2f} {unidad}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TiB"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar():
    # ... (Misma lógica de siempre) ...
    url = request.form.get('url')
    if not url: return jsonify({'error': 'Falta URL'}), 400
    try:
        ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            es_playlist = 'entries' in info
            
            thumb = info.get('thumbnail')
            if info.get('thumbnails'): thumb = info['thumbnails'][-1].get('url', thumb)

            datos = {
                'titulo': info.get('title'),
                'es_playlist': es_playlist,
                'miniatura': thumb,
                'formatos': []
            }

            if not es_playlist:
                formats = info.get('formats', [])
                resoluciones = set()
                opciones = []
                opciones.append({'id': 'bestaudio/best', 'texto': 'Solo Audio', 'ext': 'mp3', 'tipo': 'audio'})
                video_formats = [f for f in formats if f.get('height') and f.get('vcodec') != 'none']
                video_formats.sort(key=lambda x: x['height'], reverse=True)
                for f in video_formats:
                    res = f"{f['height']}p"
                    if res not in resoluciones:
                        resoluciones.add(res)
                        fid = f"bestvideo[height<={f['height']}]+bestaudio/best[height<={f['height']}]"
                        opciones.append({'id': fid, 'texto': f"Video {res}", 'ext': f.get('ext','mp4'), 'tipo': 'video'})
                datos['formatos'] = opciones
            else:
                datos['cantidad'] = len(list(info['entries']))
                datos['formatos'] = [
                    {'id': 'bestaudio/best', 'texto': 'Playlist Completa', 'ext': 'mp3', 'tipo': 'audio'},
                    {'id': 'bestvideo+bestaudio/best', 'texto': 'Playlist Completa', 'ext': 'video', 'tipo': 'video'}
                ]
            return jsonify(datos)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bajar_archivo')
def bajar_archivo():
    relative_path = request.args.get('name')
    full_path = os.path.join(BASE_TEMP_FOLDER, relative_path)
    
    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True)
    else:
        return "El archivo ya expiró o fue eliminado.", 404

@app.route('/descargar_stream')
def descargar_stream():
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    es_playlist = request.args.get('es_playlist') == 'true'

    cola = queue.Queue()
    session_id = str(uuid.uuid4())
    session_folder = os.path.join(BASE_TEMP_FOLDER, session_id)
    
    if not os.path.exists(session_folder):
        os.makedirs(session_folder)

    def tarea_descarga():
        errores = []
        completados = 0
        
        opciones = {
            'format': format_id,
            'quiet': True, 'no_warnings': True, 'ignoreerrors': True,
            'merge_output_format': 'mkv',
            'outtmpl': os.path.join(session_folder, '%(title)s.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}] if 'bestaudio' in format_id and 'bestvideo' not in format_id else []
        }

        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info: items = list(info['entries'])
                else: items = [info]

            total = len(items)
            cola.put({'status': 'inicio_total', 'total': total})

            for i, item in enumerate(items):
                idx = i + 1
                titulo = item.get('title', f'Video {idx}')
                link = item.get('url') or item.get('webpage_url')

                cola.put({'status': 'nuevo_video', 'indice': idx, 'total': total, 'titulo': titulo})

                def progress(d):
                    if d['status'] == 'downloading':
                        descargado = d.get('downloaded_bytes', 0)
                        tot = d.get('total_bytes') or d.get('total_bytes_estimate')
                        p = (descargado / tot * 100) if tot else 0
                        speed = d.get('speed')
                        cola.put({
                            'status': 'descargando', 'progreso': p,
                            'texto_avance': f"{formatear_bytes(descargado)} de {formatear_bytes(tot)}",
                            'texto_velocidad': f"{formatear_bytes(speed)}/s" if speed else "..."
                        })

                opts_video = opciones.copy()
                opts_video['progress_hooks'] = [progress]

                try:
                    with yt_dlp.YoutubeDL(opts_video) as ydl_item:
                        ydl_item.download([link])
                    completados += 1
                except Exception as e:
                    errores.append({'titulo': titulo, 'causa': str(e)})

            # Buscar archivo final
            archivos = os.listdir(session_folder)
            archivo_final_nombre = None
            if archivos:
                archivo_real = archivos[0]
                archivo_final_nombre = os.path.join(session_id, archivo_real)

            cola.put({
                'status': 'fin_total', 
                'completados': completados, 
                'errores': errores,
                'archivo_descarga': archivo_final_nombre
            })

        except Exception as e:
            cola.put({'error': str(e)})
        
        cola.put(None)

    def generador_sse():
        hilo = threading.Thread(target=tarea_descarga)
        hilo.start()
        while True:
            try:
                dato = cola.get(timeout=0.1)
                if dato is None: break
                yield f"data:{json.dumps(dato)}\n\n"
            except queue.Empty:
                if not hilo.is_alive(): break
                continue

    return Response(stream_with_context(generador_sse()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, threaded=True, host='0.0.0.0')
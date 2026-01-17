import os
import json
import subprocess
import sys
import threading
import queue
import time
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

app = Flask(__name__)

# --- Función Auxiliar para formatear números (bytes -> MB) ---
def formatear_bytes(num_bytes):
    if num_bytes is None: return "0 B"
    for unidad in ['B', 'KiB', 'MiB', 'GiB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unidad}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} TiB"

# --- Módulo de Ventana Flotante ---
def abrir_dialogo_externo():
    script_dialogo = """
import tkinter as tk
from tkinter import filedialog
import ctypes
import sys
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except: pass

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
ruta = filedialog.askdirectory(title="Selecciona Carpeta de Destino")
if ruta: print(ruta)
else: print("CANCELADO")
root.destroy()
"""
    try:
        resultado = subprocess.check_output(
            [sys.executable, "-c", script_dialogo], 
            universal_newlines=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        return resultado.strip()
    except Exception:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pedir_ruta_sistema', methods=['POST'])
def pedir_ruta_sistema():
    ruta = abrir_dialogo_externo()
    if ruta and ruta != "CANCELADO":
        return jsonify({'ruta': ruta})
    elif ruta == "CANCELADO":
        return jsonify({'cancelado': True})
    else:
        return jsonify({'error': 'Error al abrir ventana'}), 500

@app.route('/analizar', methods=['POST'])
def analizar():
    url = request.form.get('url')
    if not url: return jsonify({'error': 'Falta URL'}), 400
    try:
        ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            es_playlist = 'entries' in info
            
            # Extraemos la miniatura de alta calidad si es posible
            thumbnails = info.get('thumbnails', [])
            thumb_url = info.get('thumbnail')
            if thumbnails:
                # Intentamos buscar la última que suele ser la mejor
                thumb_url = thumbnails[-1].get('url', thumb_url)

            datos = {
                'titulo': info.get('title'),
                'es_playlist': es_playlist,
                'miniatura': thumb_url, # Enviamos la URL de la imagen
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
                        format_id = f"bestvideo[height<={f['height']}]+bestaudio/best[height<={f['height']}]"
                        opciones.append({'id': format_id, 'texto': f"Video {res}", 'ext': f.get('ext', 'mp4'), 'tipo': 'video'})
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

@app.route('/descargar_stream')
def descargar_stream():
    url = request.args.get('url')
    format_id = request.args.get('format_id')
    save_path = request.args.get('path')
    es_playlist = request.args.get('es_playlist') == 'true'

    cola_mensajes = queue.Queue()

    def trabajador_descarga():
        errores = []
        completados = 0
        total_items = 1

        base_opts = {
            'format': format_id,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}] if 'bestaudio' in format_id and 'bestvideo' not in format_id else [],
            'merge_output_format': 'mkv'
        }

        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl_scan:
                info_scan = ydl_scan.extract_info(url, download=False)
                if 'entries' in info_scan:
                    lista_videos = list(info_scan['entries'])
                    total_items = len(lista_videos)
                    playlist_title = info_scan.get('title', 'Playlist')
                    final_path = os.path.join(save_path, playlist_title)
                else:
                    lista_videos = [info_scan]
                    total_items = 1
                    final_path = save_path

            cola_mensajes.put({'status': 'inicio_total', 'total': total_items})

            for index, video in enumerate(lista_videos):
                vid_idx = index + 1
                vid_title = video.get('title', f'Video {vid_idx}')
                vid_url = video.get('url') or video.get('webpage_url')

                cola_mensajes.put({'status': 'nuevo_video', 'indice': vid_idx, 'total': total_items, 'titulo': vid_title})

                def progress_hook(d):
                    if d['status'] == 'downloading':
                        # --- CÁLCULO MATEMÁTICO DEL PORCENTAJE ---
                        downloaded = d.get('downloaded_bytes', 0)
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        
                        if total:
                            # Calculamos porcentaje nosotros mismos
                            p = (downloaded / total) * 100
                        else:
                            p = 0
                        
                        speed = d.get('speed')

                        msg = {
                            'status': 'descargando',
                            'progreso': p, # Enviamos el número flotante puro
                            'detalle': f"{formatear_bytes(downloaded)} de {formatear_bytes(total)}",
                            'velocidad': f"{formatear_bytes(speed)}/s" if speed else "..."
                        }
                        cola_mensajes.put(msg)

                current_opts = base_opts.copy()
                current_opts['outtmpl'] = os.path.join(final_path, '%(title)s.%(ext)s')
                current_opts['progress_hooks'] = [progress_hook]
                
                try:
                    with yt_dlp.YoutubeDL(current_opts) as ydl_item:
                        ydl_item.download([vid_url])
                    completados += 1
                except Exception as e:
                    err_msg = str(e)
                    if "Private video" in err_msg: err_msg = "Video Privado"
                    elif "Copyright" in err_msg: err_msg = "Bloqueo por Copyright"
                    errores.append({'indice': vid_idx, 'titulo': vid_title, 'causa': err_msg})

            cola_mensajes.put({'status': 'completado_total', 'completados': completados, 'errores': errores})

        except Exception as e:
            cola_mensajes.put({'error': str(e)})
        
        cola_mensajes.put(None) 

    def generar_sse():
        hilo = threading.Thread(target=trabajador_descarga)
        hilo.start()
        while True:
            try:
                dato = cola_mensajes.get(timeout=0.1)
                if dato is None: break
                yield f"data:{json.dumps(dato)}\n\n"
            except queue.Empty:
                if not hilo.is_alive(): break
                continue

    return Response(stream_with_context(generar_sse()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
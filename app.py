import os
import json
import subprocess
import sys
import traceback
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

app = Flask(__name__)

# --- (Mantener la función abrir_dialogo_externo igual que antes) ---
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
    # --- (Mantener igual que la versión anterior) ---
    url = request.form.get('url')
    if not url: return jsonify({'error': 'Falta URL'}), 400
    try:
        ydl_opts = {'quiet': True, 'extract_flat': 'in_playlist'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            es_playlist = 'entries' in info
            
            datos = {
                'titulo': info.get('title'),
                'es_playlist': es_playlist,
                'miniatura': info.get('thumbnail'),
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

    def generar():
        # Listas para reporte final
        errores = []
        completados = 0
        total_items = 1

        # Configuración base de yt-dlp
        base_opts = {
            'format': format_id,
            'quiet': True,
            'no_warnings': True,
            # Importante: No paramos por errores dentro de yt-dlp, los manejamos fuera
            'ignoreerrors': True, 
            'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}] if 'bestaudio' in format_id and 'bestvideo' not in format_id else [],
            'merge_output_format': 'mkv'
        }

        try:
            # 1. Obtener lista de URLs a procesar
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl_scan:
                info_scan = ydl_scan.extract_info(url, download=False)
                
                if 'entries' in info_scan:
                    # Es playlist
                    lista_videos = list(info_scan['entries'])
                    total_items = len(lista_videos)
                    playlist_title = info_scan.get('title', 'Playlist_Sin_Nombre')
                    # Carpeta de playlist
                    final_path = os.path.join(save_path, playlist_title)
                else:
                    # Es video único
                    lista_videos = [info_scan]
                    total_items = 1
                    final_path = save_path

            # Enviar evento de inicio
            yield f"data:{json.dumps({'status': 'inicio_total', 'total': total_items})}\n\n"

            # 2. Iterar manualmente video por video
            for index, video in enumerate(lista_videos):
                vid_idx = index + 1
                vid_title = video.get('title', f'Video {vid_idx}')
                vid_url = video.get('url') or video.get('webpage_url') # A veces la key cambia

                # Informar al frontend qué video estamos bajando
                msg_inicio = {'status': 'nuevo_video', 'indice': vid_idx, 'total': total_items, 'titulo': vid_title}
                yield f"data:{json.dumps(msg_inicio)}\n\n"

                # Hook de progreso para el video actual
                def progress_hook(d):
                    if d['status'] == 'downloading':
                        p = d.get('_percent_str', '0%').replace('%','')
                        try: float(p)
                        except: p = "0"
                        # Enviamos progreso parcial
                        yield f"data:{json.dumps({'status': 'descargando', 'progreso': p})}\n\n"

                # Configurar opciones para ESTE video específico
                current_opts = base_opts.copy()
                current_opts['outtmpl'] = os.path.join(final_path, '%(title)s.%(ext)s')
                current_opts['progress_hooks'] = [progress_hook]
                
                try:
                    # INTENTO DE DESCARGA
                    with yt_dlp.YoutubeDL(current_opts) as ydl_item:
                        # Si el video es privado, yt-dlp lanzará excepción o warning
                        ydl_item.download([vid_url])
                    completados += 1
                    
                except Exception as e:
                    # CAPTURA DE ERROR: No detenemos el bucle, solo registramos
                    err_msg = str(e)
                    # Limpiamos el mensaje de error para que no sea gigante
                    if "Private video" in err_msg: err_msg = "Video Privado (Requiere acceso)"
                    elif "Copyright" in err_msg: err_msg = "Bloqueo por Copyright"
                    
                    print(f"Error en video {vid_idx}: {err_msg}") # Log en consola
                    errores.append({'indice': vid_idx, 'titulo': vid_title, 'causa': err_msg})

            # 3. Reporte Final
            final_data = {
                'status': 'completado_total',
                'completados': completados,
                'errores': errores
            }
            yield f"data:{json.dumps(final_data)}\n\n"

        except Exception as e:
            # Error catastrófico (ej. se fue el internet al inicio)
            yield f"data:{json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generar()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, threaded=True)
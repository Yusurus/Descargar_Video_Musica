# 🎥 Descargador de Video y Música

Una aplicación web simple y elegante para descargar videos y música de YouTube en múltiples formatos y resoluciones.

## ✨ Características

- 🎬 **Descarga de videos** en múltiples resoluciones (hasta 4K)
- 🎵 **Extracción de audio** en formato MP3
- 📊 **Soporte para playlists** de YouTube
- 🎨 **Interfaz moderna y responsiva** basada en web
- 🧹 **Limpieza automática** de archivos temporales
- 📊 **Información detallada** de formatos disponibles
- ⚡ **Descarga rápida** y eficiente
- 📱 **Compatible con dispositivos móviles**

## 🔧 Requisitos Previos

- Python 3.7 o superior
- pip (gestor de paquetes de Python)

## 📥 Instalación

### 1. Clonar o descargar el proyecto

```bash
cd tu_directorio_del_proyecto
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

Las dependencias principales son:
- **Flask**: Framework web para Python
- **yt-dlp**: Herramienta para descargar contenido de YouTube

## 🚀 Uso

### Iniciar la aplicación

```bash
python app.py
```

La aplicación estará disponible en `http://localhost:5000`

### Pasos para descargar

1. Abre la aplicación en tu navegador
2. Pega la URL de YouTube (video, canal o playlist)
3. Haz clic en "Analizar"
4. Selecciona el formato deseado:
   - **Solo Audio**: Descarga el audio en MP3
   - **Video**: Elige tu resolución preferida (480p, 720p, 1080p, etc.)
5. Haz clic en descargar
6. El archivo se descargará automáticamente

## 📁 Estructura del Proyecto

```
Descargar_Video_Musica/
├── app.py                 # Aplicación principal de Flask
├── requirements.txt       # Dependencias del proyecto
├── templates/
│   └── index.html        # Interfaz web (HTML/CSS/JavaScript)
└── temp_downloads/       # Carpeta para archivos temporales
    └── (Archivos se eliminan automáticamente)
```

## ⚙️ Configuración

### Cambiar tiempo de expiración de archivos

En `app.py`, modifica esta línea (actualmente 10 minutos):

```python
TIEMPO_EXPIRACION_MINUTOS = 10  # Cambia este valor
```

### Cambiar puerto

Si necesitas ejecutar en otro puerto, puedes modificar:

```bash
python app.py --port 8080
```

## 🔒 Notas Importantes

⚠️ **Responsabilidad Legal**: 
- Asegúrate de que tienes permiso para descargar el contenido
- Respeta los derechos de autor y los términos de servicio de YouTube
- Esta herramienta es solo para uso personal
- El autor no se responsabiliza del uso indebido

## 🛠️ Solución de Problemas

### Error: "ModuleNotFoundError: No module named 'flask'"
```bash
pip install Flask
```

### Error: "ModuleNotFoundError: No module named 'yt_dlp'"
```bash
pip install yt-dlp
```

### Los archivos no se descargan
- Verifica tu conexión a internet
- Comprueba que la URL de YouTube es válida
- Intenta actualizar yt-dlp: `pip install --upgrade yt-dlp`

## 📊 Características Técnicas

- **Sistema de limpieza automática**: Los archivos temporales se eliminan automáticamente después de 10 minutos
- **Multi-threading**: La limpieza se ejecuta en segundo plano sin afectar la interfaz
- **Gestión inteligente de formatos**: Detecta automáticamente las mejores opciones disponibles
- **Manejo robusto de errores**: Proporciona mensajes de error claros

## 🎯 Versión

v1.0 - Primera versión estable

## 📝 Licencia

Uso personal. Respeta los derechos de autor del contenido que descargas.

## 🤝 Contribuciones

Si encuentras bugs o tienes sugerencias, siéntete libre de reportarlos.

---

**Disfruta descargando contenido de YouTube de forma segura y legal** 🎉

"""Start the personal app and open the browser only after it responds."""
import threading
import time
import urllib.request
import webbrowser
import socket
import uvicorn


def open_when_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1) as response:
                if response.status == 200:
                    webbrowser.open('http://127.0.0.1:8000/')
                    return
        except OSError:
            time.sleep(0.5)
    print('No se pudo abrir el navegador. Revisa los errores del servidor.')


if __name__ == '__main__':
    with socket.socket() as check:
        try:
            check.bind(('127.0.0.1', 8000))
        except OSError:
            raise SystemExit('El puerto 8000 ya esta ocupado. Cierra la app anterior e intentalo de nuevo.')
    threading.Thread(target=open_when_ready, daemon=True).start()
    print('Deja esta ventana abierta mientras usas Clip Studio. Ctrl+C para cerrar.')
    uvicorn.run('app:app', host='127.0.0.1', port=8000)

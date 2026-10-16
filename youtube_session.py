"""Cleanup for the withdrawn automated YouTube login.

Google rejected the controlled browser on the user's PC. No operation in this
module launches a browser, reads cookies, or attempts authentication.
"""
import shutil
from pathlib import Path

RETIRED = ('La conexión integrada se retiró porque Google rechazó el navegador controlado. '
           'No vuelvas a iniciar sesión en esa ventana. La importación por enlace sigue '
           'sin estar resuelta para videos que exigen acceso adicional.')


class SessionUnavailable(ValueError):
    pass


class YouTubeSession:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.marker = self.directory / 'authorized'

    def status(self):
        return {'authorized': self.marker.exists(), 'connected': False,
                'cleanup_pending': (self.directory / 'profile').exists(), 'message': RETIRED}

    def connect(self):
        raise SessionUnavailable(RETIRED)

    def cookies(self):
        raise SessionUnavailable(RETIRED)

    def download_context(self):
        raise SessionUnavailable(RETIRED)

    def disconnect(self):
        # Only the app-owned directory, never a normal browser profile.
        self.marker.unlink(missing_ok=True)
        try:
            shutil.rmtree(self.directory / 'profile')
        except FileNotFoundError:
            pass
        except OSError:
            raise SessionUnavailable(
                'La autorización se retiró, pero el perfil propio sigue ocupado. '
                'Cierra la ventana de conexión anterior y pulsa Eliminar conexión anterior otra vez.') from None
        return self.status()


session = YouTubeSession(Path(__file__).parent / 'data' / 'youtube-session')

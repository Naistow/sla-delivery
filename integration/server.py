from .api import create_app
from .repository import MssqlRepository, connect_mssql
from .settings import Settings

app = create_app(MssqlRepository(connect_mssql(Settings.from_env())))

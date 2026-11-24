import os
from pathlib import Path

APP = Path(__file__).resolve().parent
HOME = Path(os.environ.get('OPTIBID_HOME', APP if (APP / 'optibid.db').is_file() else APP.parent)).resolve()
ARCHIVE = Path(os.environ.get('OPTIBID_ARSIV_DB', HOME / 'optibid.db')).resolve()
DATA = Path(os.environ['OPTIBID_HOME']).resolve() / 'IhaleAsistani/data' if 'OPTIBID_HOME' in os.environ else APP / 'data'

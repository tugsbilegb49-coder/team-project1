from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from src.logger import CSVActivityLogger, load_log


def test_explicit_camera_end_time_keeps_old_csv_format_readable():
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'camera.csv'
        path.write_text('timestamp,state,duration_seconds\n2026-11-06T10:00:00,WORKING,5\n')
        logger = CSVActivityLogger(str(path))
        logger.log('IDLE', 3, timestamp=datetime(2026, 11, 6, 2, 1, tzinfo=timezone.utc))
        logger.close()
        rows = load_log(str(path))
        assert len(rows) == 2
        assert rows['duration_seconds'].sum() == 8
        assert rows['timestamp'].dt.tz is None

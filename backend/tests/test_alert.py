"""故障预警回归测试。"""

from app.routers.alert import _risk_devices


def test_risk_devices_handles_sqlite_datetimes(db_session):
    """SQLite 返回无时区 datetime 时，近 30 天统计不应抛出异常。"""
    rows = _risk_devices(db_session)
    assert isinstance(rows, list)


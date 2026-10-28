"""일정 계산 테스트 (SPEC 6.6)."""

from datetime import datetime, timedelta, timezone

import pytest

from bot.scheduler import BUILTIN_SCHEDULES, CronError, is_due, latest_due, parse_cron

KST = timezone(timedelta(hours=9))
# 2026-10-28은 수요일
WED_0900 = datetime(2026, 10, 28, 9, 0, tzinfo=KST)


def test_daily_latest_due():
    cron = parse_cron(BUILTIN_SCHEDULES["morning_report"])
    assert latest_due(cron, WED_0900) == datetime(2026, 10, 28, 8, 0, tzinfo=KST)
    before = WED_0900.replace(hour=7, minute=59)
    assert latest_due(cron, before) == datetime(2026, 10, 27, 8, 0, tzinfo=KST)


def test_weekly_runs_on_monday():
    cron = parse_cron(BUILTIN_SCHEDULES["weekly_report"])
    assert latest_due(cron, WED_0900) == datetime(2026, 10, 26, 8, 0, tzinfo=KST)


def test_lists_and_sunday_as_seven():
    cron = parse_cron("0,30 3,15 * * 7")
    sunday = datetime(2026, 11, 1, 16, 0, tzinfo=KST)
    assert latest_due(cron, sunday) == datetime(2026, 11, 1, 15, 30, tzinfo=KST)


def test_missed_runs_catch_up_once():
    cron = parse_cron("0 8 * * *")
    # 3일 동안 꺼져 있었다: 한 번만 실행한다
    last = datetime(2026, 10, 25, 8, 0, tzinfo=KST)
    assert is_due(cron, WED_0900, last)
    assert not is_due(cron, WED_0900, WED_0900)
    # 처음 켤 때는 한 번 실행한다
    assert is_due(cron, WED_0900, None)
    # 오늘 08:00 실행 뒤에는 내일 08:00 전까지 다시 하지 않는다
    after = datetime(2026, 10, 28, 8, 0, 5, tzinfo=KST)
    assert not is_due(cron, WED_0900.replace(hour=23), after)


@pytest.mark.parametrize(
    "text", ["0 8 * *", "0 8 1 * *", "0 8 * 10 *", "60 8 * * *", "0 24 * * *", "*/5 * * * *"]
)
def test_unsupported_cron_is_rejected(text):
    with pytest.raises(CronError):
        parse_cron(text)

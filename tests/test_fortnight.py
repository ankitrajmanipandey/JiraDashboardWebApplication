import unittest
from datetime import date, datetime, timedelta, timezone

from app import (
    build_fortnight_jql,
    count_issues_by_fortnight,
    fortnight_bounds,
    last_six_fortnights,
)


IST = timezone(timedelta(hours=5, minutes=30))


def issue(key, created):
    return {"key": key, "fields": {"created": created}}


class FortnightBoundsTests(unittest.TestCase):
    def test_30_day_month(self):
        self.assertEqual(fortnight_bounds(2026, 11, 1), (date(2026, 11, 1), date(2026, 11, 15)))
        self.assertEqual(fortnight_bounds(2026, 11, 2), (date(2026, 11, 16), date(2026, 11, 30)))
        self.assertEqual(fortnight_bounds(2026, 9, 2), (date(2026, 9, 16), date(2026, 9, 30)))
        self.assertEqual(fortnight_bounds(2026, 4, 2), (date(2026, 4, 16), date(2026, 4, 30)))

    def test_31_day_month(self):
        self.assertEqual(fortnight_bounds(2026, 10, 1), (date(2026, 10, 1), date(2026, 10, 15)))
        self.assertEqual(fortnight_bounds(2026, 10, 2), (date(2026, 10, 16), date(2026, 10, 31)))
        self.assertEqual(fortnight_bounds(2026, 1, 2), (date(2026, 1, 16), date(2026, 1, 31)))
        self.assertEqual(fortnight_bounds(2026, 12, 2), (date(2026, 12, 16), date(2026, 12, 31)))

    def test_february_28_days(self):
        self.assertEqual(fortnight_bounds(2026, 2, 1), (date(2026, 2, 1), date(2026, 2, 14)))
        self.assertEqual(fortnight_bounds(2026, 2, 2), (date(2026, 2, 15), date(2026, 2, 28)))

    def test_february_29_days(self):
        self.assertEqual(fortnight_bounds(2024, 2, 1), (date(2024, 2, 1), date(2024, 2, 14)))
        self.assertEqual(fortnight_bounds(2024, 2, 2), (date(2024, 2, 15), date(2024, 2, 29)))
        self.assertEqual(fortnight_bounds(2028, 2, 2), (date(2028, 2, 15), date(2028, 2, 29)))


class LastSixFortnightsTests(unittest.TestCase):
    def test_current_date_23_november_2026(self):
        periods = last_six_fortnights(date(2026, 11, 23))
        self.assertEqual(
            periods,
            [
                (date(2026, 9, 1), date(2026, 9, 15)),
                (date(2026, 9, 16), date(2026, 9, 30)),
                (date(2026, 10, 1), date(2026, 10, 15)),
                (date(2026, 10, 16), date(2026, 10, 31)),
                (date(2026, 11, 1), date(2026, 11, 15)),
                (date(2026, 11, 16), date(2026, 11, 30)),
            ],
        )

    def test_first_fortnight_is_current(self):
        periods = last_six_fortnights(date(2026, 11, 10))
        self.assertEqual(periods[-1], (date(2026, 11, 1), date(2026, 11, 15)))
        self.assertEqual(periods[0], (date(2026, 8, 16), date(2026, 8, 31)))

    def test_year_transition_into_january(self):
        periods = last_six_fortnights(date(2027, 1, 10))
        self.assertEqual(
            periods,
            [
                (date(2026, 10, 16), date(2026, 10, 31)),
                (date(2026, 11, 1), date(2026, 11, 15)),
                (date(2026, 11, 16), date(2026, 11, 30)),
                (date(2026, 12, 1), date(2026, 12, 15)),
                (date(2026, 12, 16), date(2026, 12, 31)),
                (date(2027, 1, 1), date(2027, 1, 15)),
            ],
        )

    def test_december_second_fortnight_crosses_into_new_year_window(self):
        periods = last_six_fortnights(date(2026, 12, 20))
        self.assertEqual(periods[0], (date(2026, 10, 1), date(2026, 10, 15)))
        self.assertEqual(periods[-1], (date(2026, 12, 16), date(2026, 12, 31)))

    def test_leap_year_february_second_fortnight(self):
        periods = last_six_fortnights(date(2024, 2, 20))
        self.assertEqual(periods[-2], (date(2024, 2, 1), date(2024, 2, 14)))
        self.assertEqual(periods[-1], (date(2024, 2, 15), date(2024, 2, 29)))

    def test_non_leap_february_second_fortnight(self):
        periods = last_six_fortnights(date(2026, 2, 20))
        self.assertEqual(periods[-2], (date(2026, 2, 1), date(2026, 2, 14)))
        self.assertEqual(periods[-1], (date(2026, 2, 15), date(2026, 2, 28)))


class TicketAggregationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 23)
        self.periods = last_six_fortnights(self.today)

    def test_counts_by_created_date_and_keeps_empty_fortnights_at_zero(self):
        issues = [
            issue("TC-1", "2026-09-01T00:30:00.000+0530"),
            issue("TC-2", "2026-09-15T23:59:00.000+0530"),
            issue("TC-3", "2026-11-16T09:00:00.000+0530"),
            issue("TC-4", "2026-11-23T18:00:00.000+0530"),
        ]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(counts, [2, 0, 0, 0, 0, 2])

    def test_each_issue_key_is_counted_once(self):
        issues = [
            issue("TC-1", "2026-11-20T09:00:00.000+0530"),
            issue("TC-1", "2026-11-20T09:00:00.000+0530"),
        ]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(counts, [0, 0, 0, 0, 0, 1])

    def test_future_dates_inside_the_current_fortnight_are_excluded(self):
        issues = [
            issue("TC-1", "2026-11-23T10:00:00.000+0530"),
            issue("TC-2", "2026-11-24T10:00:00.000+0530"),
            issue("TC-3", "2026-11-30T10:00:00.000+0530"),
        ]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(counts, [0, 0, 0, 0, 0, 1])

    def test_uses_created_timestamp_in_the_application_timezone(self):
        # 2026-11-15 20:00 UTC is 2026-11-16 01:30 IST, so it belongs to the second fortnight.
        issues = [issue("TC-9", "2026-11-15T20:00:00.000+0000")]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(counts, [0, 0, 0, 0, 0, 1])

    def test_updated_date_is_ignored(self):
        issues = [{
            "key": "TC-8",
            "fields": {
                "created": "2026-09-02T08:00:00.000+0530",
                "updated": "2026-11-22T08:00:00.000+0530",
            },
        }]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(counts, [1, 0, 0, 0, 0, 0])

    def test_zero_tickets(self):
        counts = count_issues_by_fortnight([], self.periods, self.today, IST)
        self.assertEqual(counts, [0, 0, 0, 0, 0, 0])

    def test_jql_covers_oldest_fortnight_through_today_only(self):
        jql = build_fortnight_jql("TC", self.periods[0][0], self.today)
        self.assertIn("project = TC", jql)
        self.assertIn('created >= "2026-09-01"', jql)
        self.assertIn('created < "2026-11-24"', jql)
        self.assertNotIn("updated", jql.lower())

    def test_naive_boundary_datetime_uses_utc_then_local_date(self):
        parsed_day = datetime(2026, 11, 15, 20, 0, tzinfo=timezone.utc)
        issues = [issue("TC-7", parsed_day.isoformat())]
        counts = count_issues_by_fortnight(issues, self.periods, self.today, IST)
        self.assertEqual(sum(counts), 1)


if __name__ == "__main__":
    unittest.main()

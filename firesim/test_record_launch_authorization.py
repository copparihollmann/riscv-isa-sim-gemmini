import datetime as dt
import unittest
from record_launch_authorization import requested_expiry


class ExpiryTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 9, 0, 19, tzinfo=dt.timezone.utc)

    def test_exact_user_deadline_is_not_extended_to_default_horizon(self):
        expiry = requested_expiry('2026-11-09T02:30:00Z', self.now)
        self.assertEqual(expiry, dt.datetime(2026, 11, 9, 2, 30, tzinfo=dt.timezone.utc))

    def test_rejects_naive_expired_or_outside_horizon(self):
        for value in ['2026-11-09T02:30:00', '2026-11-09T00:19:00Z',
                      '2026-11-09T00:18:00Z', '2026-11-09T06:20:00Z']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                requested_expiry(value, self.now)

    def test_normalizes_offset_and_keeps_existing_default_horizon(self):
        self.assertEqual(requested_expiry('2026-11-08T18:30:00-08:00', self.now),
                         requested_expiry('2026-11-09T02:30:00Z', self.now))
        self.assertEqual(requested_expiry(None, self.now), self.now + dt.timedelta(hours=6))


if __name__ == '__main__':
    unittest.main()

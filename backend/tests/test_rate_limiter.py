import unittest

from app.services.rate_limiter import RateLimitExceeded, SlidingWindowRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_blocks_requests_over_limit_and_reports_retry_after(self):
        now = [100.0]
        limiter = SlidingWindowRateLimiter(2, 60, clock=lambda: now[0])

        limiter.consume("gemini:thread-1")
        now[0] = 110.0
        limiter.consume("gemini:thread-1")

        with self.assertRaises(RateLimitExceeded) as error:
            limiter.consume("gemini:thread-1")

        self.assertEqual(error.exception.retry_after_seconds, 50)

    def test_allows_request_after_window_and_isolates_keys(self):
        now = [100.0]
        limiter = SlidingWindowRateLimiter(1, 10, clock=lambda: now[0])

        limiter.consume("gemini:thread-1")
        limiter.consume("gemini:thread-2")
        now[0] = 110.0
        limiter.consume("gemini:thread-1")


if __name__ == "__main__":
    unittest.main()

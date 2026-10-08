from types import SimpleNamespace

from cykelfest_routing.geocoding import AddressWorker


class FakeGeocoder:
    domain = "test"

    def __init__(self):
        self.calls = []

    def geocode(self, address, **kwargs):
        self.calls.append(address)
        if address == "unknown":
            return None
        if address == "offline":
            raise TimeoutError("connection timed out")
        return SimpleNamespace(latitude=59.3, longitude=18.1)


def test_lookup_caches_duplicate_addresses_and_reports_no_match(tmp_path):
    provider = FakeGeocoder()
    worker = AddressWorker(
        [("a", "Street"), ("b", "Street"), ("c", "unknown")],
        tmp_path / "cache.json",
        geocoder=provider,
        interval=0,
    )
    reports = []
    worker.results_ready.connect(reports.append)
    worker.run()
    assert provider.calls == ["Street", "unknown"]
    assert len(reports[0]["results"]) == 2
    assert "no match" in reports[0]["problems"][0]
    worker = AddressWorker(
        [("d", "Street")], tmp_path / "cache.json", geocoder=provider, interval=0
    )
    worker.run()
    assert provider.calls == ["Street", "unknown"]


def test_failure_stops_remaining_requests_and_cancellation_keeps_completed_results(tmp_path):
    provider = FakeGeocoder()
    worker = AddressWorker(
        [("a", "Street"), ("b", "offline"), ("c", "Other")],
        tmp_path / "cache.json",
        geocoder=provider,
        interval=0,
    )
    reports = []
    worker.results_ready.connect(reports.append)
    worker.run()
    assert provider.calls == ["Street", "offline"]
    assert len(reports[0]["results"]) == 1
    assert "lookup failed" in reports[0]["problems"][0]
    worker = AddressWorker(
        [("a", "Street"), ("b", "Other")], tmp_path / "cache.json", geocoder=provider, interval=0
    )
    reports.clear()
    worker.results_ready.connect(reports.append)
    worker.progress.connect(lambda done, total, address: worker.cancel() if done == 1 else None)
    worker.run()
    assert len(reports[0]["results"]) == 1
    assert reports[0]["cancelled"]

from router_consumer_a2a import RouterA2A

if __name__ == "__main__":
    router = RouterA2A()
    envelope = {
        "task": "USER_QUERY",
        "payload": {
            "query": "Show my spending by merchant for the last 30 days",
            "json_path": "/mnt/data/simulated_bank_data_single.json",
            "window": {"since": "2025-08-28", "until": "2025-09-27"},
            "currency": "USD",
            "traceId": "demo-1"
        }
    }
    result = router.route(envelope)
    import json
    print(json.dumps(result, indent=2))

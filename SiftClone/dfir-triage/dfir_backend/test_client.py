import json

from server import agent_run_case, create_suspicious_demo_bundle, list_all_cases


def show(raw: str) -> dict:
    data = json.loads(raw)
    print(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    print("STEP 1 - Create deterministic demo cases")
    show(create_suspicious_demo_bundle(reset=True))

    print("STEP 2 - List cases")
    show(list_all_cases())

    print("STEP 3 - Run agent controller on persistence demo")
    result = show(agent_run_case("CASE-DEMO-PERSISTENCE-001"))
    if result.get("status") != "ok":
        raise SystemExit(f"Agent run failed: {result.get('validation')}")

    print("Smoke test complete.")

# Ollie Agent — Migration SRE Copilot

A small demo agent that translates Datadog monitoring artifacts (queries, alerts, dashboards) into Prometheus alerting rules and Grafana dashboards.

You can interact with the agent here:
https://huggingface.co/spaces/kminutti/ollie-agent-demo

## Key components

- `agent.py` — Core agent implementation. Contains system prompts, the translation loop, validation helpers, and the self-correction logic.
- `app.py` — Streamlit UI that demonstrates the agent (translate queries/alerts or dashboards). Uses `create_agent()` from `agent.py`.
- `demo/` — Example dashboards, prometheus configs, and a small metrics generator used for demonstration and local testing.
- `requirements.txt` — Python dependencies for running the demo UI and agent.

## How it works (agent approach)

1. The UI (or an API consumer) sends a Datadog query or dashboard JSON to the agent.
2. The agent prompts an LLM (configured in `MigrationAgent`) with strict system instructions to produce a single JSON object containing:
   - reasoning (why/how the translation was done)
   - `rule_yaml` and `test_yaml` (for queries/alerts)
   - or `grafana_dashboard` (for dashboards)
3. The agent runs validation:
   - For Prometheus rules: writes the generated YAML to disk and invokes `promtool check rules` and `promtool test rules` to ensure syntax and test cases pass.
   - For Grafana dashboards: performs schema checks for required fields, panel structure, grid positions, and simple PromQL sanity checks.
4. If validation fails, the agent appends the validation errors to the conversation and asks the LLM to fix the output. This loop repeats up to `max_retries`.
5. On success, the agent returns the generated artifacts and validation logs for download/import.


## Quick start (local)

1. Install Python dependencies:

   pip install -r requirements.txt

2. Ensure `promtool` (from Prometheus) is installed and available on PATH if you want Prometheus rule validation. On macOS you can install Prometheus tooling via Homebrew or download releases.

3. Set your OpenAI API key in the environment:

   export OPENAI_API_KEY="sk-..."

4. Run the Streamlit demo UI:

   streamlit run app.py

5. Use the UI to paste a Datadog query or upload a Datadog dashboard JSON. The agent will generate Prometheus rules / Grafana dashboard JSON and run validation.

## Demo assets

The `demo/` directory contains a prometheus config, and a tiny metric generator to exercise the generated rules and tests locally.

## Trade-offs and caveats

- LLM correctness vs. determinism: LLMs can produce different (but plausible) outputs across runs. The agent reduces risk by validating with `promtool`, but nondeterminism can still affect reproducibility.

- Dependency on external tooling: Prometheus validation requires `promtool`. If it is missing (for example in some deployment environments), the agent will be unable to fully verify generated alerts.

- Cost & latency: Each translation requires one or more LLM calls. Multiple retries increase API usage and response time. Use conservative temperature and retry limits in production.

- Security & data residency: Sent prompts include user-provided queries and dashboards. Do not send sensitive or proprietary telemetry to external LLMs unless you have appropriate contracts and controls.


## Next steps / Improvements

- Add CI that runs the agent against the `demo/` assets and ensures generated rules pass in a reproducible environment (container with promtool).
- Add more robust PromQL static analysis and richer dashboard schema validation.
- Enable migration of other providers like Splunk
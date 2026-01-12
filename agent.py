import json
import subprocess
import tempfile
import os
from typing import Tuple, Optional, Dict, Any, Callable
from openai import OpenAI


# ============================================================================
# SYSTEM PROMPTS - The Agent's Instructions
# ============================================================================

QUERY_TRANSLATION_PROMPT = """You are an Expert SRE at Grafana Labs. Your role is to migrate monitoring queries from Datadog to Prometheus.

CRITICAL RULES:
1. **Naming Standards**:
   - Recording rules: snake_case (e.g., cpu_usage_percent)
   - Alert rules: PascalCase (e.g., HighCPUUsage)

2. **Best Practices**:
   - Use `avg_over_time()`, `rate()`, or `increase()` to smooth noisy metrics
   - Set meaningful alert thresholds with context
   - Include `for` duration in alerts to prevent flapping
   - Add helpful annotations and descriptions

3. **YAML Formatting - VERY IMPORTANT**:
   - Use actual newlines, not \\n escape sequences
   - Use 2 spaces for indentation (never tabs)
   - Quote strings that contain special characters like {{ }} or :
   - The rule_yaml and test_yaml fields should be plain YAML strings, not escaped strings

4. **Output Format**:
   You MUST return ONLY valid JSON with this exact structure:
   {
       "reasoning": "Brief explanation of translation logic and any assumptions made",
       "rule_yaml": "groups:\n  - name: cpu_alerts\n    interval: 30s\n    rules:\n      - alert: HighCPUUsage\n        expr: demo_cpu_usage_percent > 85\n        for: 1m\n        labels:\n          severity: warning\n        annotations:\n          summary: \"High CPU on {{ $labels.host }}\"",
       "test_yaml": "rule_files:\n  - rules.yml\ntests:\n  - interval: 1m\n    input_series:\n      - series: 'demo_cpu_usage_percent{host=\"web-1\"}'\n        values: '90 90 90 90'\n    alert_rule_test:\n      - eval_time: 2m\n        alertname: HighCPUUsage\n        exp_alerts:\n          - exp_labels:\n              severity: warning\n              host: web-1"
   }

5. **Testing**:
   - Include at least 2 test cases per rule
   - Test both passing conditions (alert fires) and edge cases
   - Use realistic metric values
   - Make sure eval_time is greater than the alert's 'for' duration

6. **Use Demo Metrics**:
   - Prefer demo_cpu_usage_percent{host="X"} for CPU
   - Use demo_memory_usage_percent{host="X"} for memory
   - Use demo_http_requests_total{service="X",status="Y"} for HTTP metrics

Remember: Output ONLY the JSON object, no markdown formatting."""


DASHBOARD_TRANSLATION_PROMPT = """You are a Staff SRE at Grafana Labs. Your role is to migrate Datadog dashboards to Grafana.

CRITICAL RULES:
1. **Queries**: Convert Datadog metrics to actual Prometheus node_exporter metrics or demo metrics
2. **Use REAL metrics available in our demo**:
   - node_cpu_seconds_total (for CPU)
   - node_memory_* (for memory)  
   - demo_cpu_usage_percent{host="X"} (for demo CPU)
   - demo_memory_usage_percent{host="X"} (for demo memory)
   - demo_http_requests_total{service="X",status="Y"} (for HTTP metrics)
3. **Panel types**: Use "timeseries" for graphs, "stat" for single values
4. **Grid layout**: Use gridPos with x, y, w (width 0-24), h (height in units)

OUTPUT FORMAT - Return ONLY valid JSON with this EXACT structure:
{
    "reasoning": "Explanation of translation decisions and which metrics you used",
    "grafana_dashboard": {
        "title": "Dashboard Name",
        "uid": "migrated-dashboard",
        "timezone": "browser",
        "schemaVersion": 16,
        "version": 0,
        "refresh": "5s",
        "time": {
            "from": "now-15m",
            "to": "now"
        },
        "panels": [
            {
                "id": 1,
                "type": "timeseries",
                "title": "Panel Title",
                "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
                "targets": [
                    {
                        "expr": "actual_prometheus_query",
                        "legendFormat": "{{instance}}",
                        "refId": "A"
                    }
                ],
                "options": {
                    "legend": {"displayMode": "list", "placement": "bottom"}
                },
                "fieldConfig": {
                    "defaults": {
                        "color": {"mode": "palette-classic"},
                        "custom": {
                            "axisPlacement": "auto",
                            "drawStyle": "line",
                            "fillOpacity": 10,
                            "lineWidth": 1,
                            "pointSize": 5,
                            "showPoints": "never"
                        },
                        "unit": "short"
                    }
                }
            }
        ]
    }
}

EXAMPLE VALID QUERIES:
- CPU: 100 - (avg by(instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
- Memory: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
- Demo CPU: demo_cpu_usage_percent{host="web-1"}
- HTTP Rate: rate(demo_http_requests_total[5m])

Remember: The dashboard object should be directly importable into Grafana. Output ONLY the JSON object."""


# ============================================================================
# VALIDATION TOOLS - The "Compiler"
# ============================================================================

def validate_prometheus_rules(rule_yaml: str, test_yaml: str) -> Tuple[bool, str]:
    """
    Validate Prometheus rules using promtool.
    
    Returns:
        (success: bool, logs: str)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        rule_path = os.path.join(tmpdir, "rules.yml")
        test_path = os.path.join(tmpdir, "tests.yml")
        
        # Write files to disk
        try:
            with open(rule_path, "w") as f:
                f.write(rule_yaml)
            with open(test_path, "w") as f:
                f.write(test_yaml)
        except Exception as e:
            return False, f"❌ Error writing YAML files: {e}"
        
        logs = []
        
        # Step 1: Syntax validation
        try:
            result = subprocess.run(
                ["promtool", "check", "rules", rule_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logs.append("✅ Syntax Check: PASSED")
                logs.append(f"   {result.stdout.strip()}")
            else:
                error_msg = f"❌ Syntax Check: FAILED\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                logs.append(error_msg)
                return False, "\n".join(logs)
        except subprocess.TimeoutExpired:
            return False, "❌ Syntax validation timeout"
        except FileNotFoundError:
            return False, "❌ promtool not found (not in container?)"
        except Exception as e:
            return False, f"❌ Syntax check error: {e}"
        
        # Step 2: Unit test execution
        try:
            result = subprocess.run(
                ["promtool", "test", "rules", test_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                logs.append("✅ Unit Tests: PASSED")
                logs.append(f"\n{result.stdout}")
                return True, "\n".join(logs)
            else:
                error_msg = f"❌ Unit Tests: FAILED\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
                logs.append(error_msg)
                return False, "\n".join(logs)
        except subprocess.TimeoutExpired:
            return False, "❌ Test execution timeout"
        except Exception as e:
            return False, f"❌ Test execution error: {e}"
    
    return False, "Unknown error"


def validate_grafana_dashboard(dashboard: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate Grafana dashboard schema.
    
    
    Returns:
        (success: bool, logs: str)
    """
    logs = []
    errors = []
    
    # Required top-level fields
    required_fields = {
        "title": str,
        "panels": list,
    }
    
    # Check required fields
    for field, expected_type in required_fields.items():
        if field not in dashboard:
            errors.append(f"Missing required field: '{field}'")
        elif not isinstance(dashboard[field], expected_type):
            errors.append(f"Field '{field}' should be {expected_type.__name__}, got {type(dashboard[field]).__name__}")
    
    if errors:
        return False, "❌ Dashboard Schema Validation: FAILED\n\n" + "\n".join(f"  • {e}" for e in errors)
    
    logs.append("✅ Required fields: PASSED")
    
    # Validate panels structure
    panels = dashboard.get("panels", [])
    
    if not panels:
        errors.append("Dashboard has no panels")
    
    for i, panel in enumerate(panels):
        panel_errors = []
        
        # Check panel required fields
        if "id" not in panel:
            panel_errors.append(f"Panel {i}: Missing 'id'")
        if "type" not in panel:
            panel_errors.append(f"Panel {i}: Missing 'type'")
        if "title" not in panel:
            panel_errors.append(f"Panel {i}: Missing 'title'")
        
        # Check gridPos (required for positioning)
        if "gridPos" in panel:
            grid = panel["gridPos"]
            required_grid_fields = ["x", "y", "w", "h"]
            for field in required_grid_fields:
                if field not in grid:
                    panel_errors.append(f"Panel {i}: gridPos missing '{field}'")
        else:
            panel_errors.append(f"Panel {i}: Missing 'gridPos'")
        
        # Check targets (queries)
        if "targets" in panel:
            targets = panel["targets"]
            if not isinstance(targets, list):
                panel_errors.append(f"Panel {i}: 'targets' should be a list")
            elif len(targets) == 0:
                panel_errors.append(f"Panel {i}: No targets (queries) defined")
            else:
                for j, target in enumerate(targets):
                    if "expr" not in target and "query" not in target:
                        panel_errors.append(f"Panel {i}, Target {j}: Missing 'expr' or 'query'")
                    if "refId" not in target:
                        panel_errors.append(f"Panel {i}, Target {j}: Missing 'refId'")
        
        errors.extend(panel_errors)
    
    if errors:
        return False, "❌ Panel Validation: FAILED\n\n" + "\n".join(f"  • {e}" for e in errors)
    
    logs.append(f"✅ Panel validation: PASSED ({len(panels)} panels)")
    
    # Check for recommended fields
    warnings = []
    
    if "uid" not in dashboard:
        warnings.append("Recommended: Add 'uid' for dashboard identification")
    if "schemaVersion" not in dashboard:
        warnings.append("Recommended: Add 'schemaVersion'")
    if "time" not in dashboard:
        warnings.append("Recommended: Add 'time' object for default time range")
    if "refresh" not in dashboard:
        warnings.append("Recommended: Add 'refresh' for auto-refresh interval")
    
    if warnings:
        logs.append("\n⚠️  Recommendations:")
        logs.extend(f"  • {w}" for w in warnings)
    
    # Validate PromQL syntax in queries (basic check)
    query_issues = []
    for i, panel in enumerate(panels):
        for j, target in enumerate(panel.get("targets", [])):
            expr = target.get("expr", "")
            if expr:
                # Basic PromQL validation
                if "{}" in expr or "[]" in expr:
                    query_issues.append(f"Panel {i}, Target {j}: Query contains empty braces/brackets")
                if expr.strip() == "":
                    query_issues.append(f"Panel {i}, Target {j}: Empty query")
    
    if query_issues:
        logs.append("\n⚠️  Query Issues:")
        logs.extend(f"  • {q}" for q in query_issues)
    
    return True, "\n".join(logs)


# ============================================================================
# AGENT CORE - Self-Correcting Translation Loop
# ============================================================================

class MigrationAgent:
    """
    The core agent that translates Datadog to Prometheus/Grafana.
    
    Key feature: Self-correction loop with compiler validation.
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    def translate_query(
        self, 
        datadog_query: str, 
        max_retries: int = 3,
        on_attempt: Optional[Callable[[int, str], None]] = None,
        on_validation: Optional[Callable[[bool, str], None]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Translate a Datadog query to Prometheus with validation.
        
        Args:
            datadog_query: The Datadog query string
            max_retries: Maximum number of retry attempts
            on_attempt: Callback for each attempt (attempt_num, reasoning)
            on_validation: Callback after validation (success, logs)
        
        Returns:
            (success, data, final_message)
        """
        messages = [
            {"role": "system", "content": QUERY_TRANSLATION_PROMPT},
            {"role": "user", "content": f"Translate this monitoring query:\n{datadog_query}"}
        ]
        
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                
                content = response.choices[0].message.content
                data = json.loads(content)
                
                # Validate response structure
                required = ["reasoning", "rule_yaml", "test_yaml"]
                missing = [k for k in required if k not in data]
                if missing:
                    raise ValueError(f"Missing required fields: {missing}")
                
                # Notify about reasoning
                if on_attempt:
                    on_attempt(attempt, data['reasoning'])
                
                # Validate with promtool
                valid, logs = validate_prometheus_rules(data['rule_yaml'], data['test_yaml'])
                
                # Notify about validation result
                if on_validation:
                    on_validation(valid, logs)
                
                if valid:
                    return True, data, logs
                else:
                    # Self-correction: feed error back to LLM
                    if attempt < max_retries:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user", 
                            "content": f"""The previous output failed validation with these errors:

{logs}

Fix the errors and generate valid YAML. Make sure:
1. YAML is properly indented (use spaces, not tabs)
2. Strings with special characters are quoted
3. Test cases use valid time series format
4. Alert expressions are valid PromQL
5. eval_time in tests is greater than the alert's 'for' duration"""
                        })
                    else:
                        return False, data, logs
                        
            except json.JSONDecodeError as e:
                if attempt == max_retries:
                    return False, None, f"JSON parsing failed: {e}"
            except Exception as e:
                if attempt == max_retries:
                    return False, None, str(e)
        
        return False, None, "Max retries reached"
    
    def translate_dashboard(
        self,
        datadog_dashboard_json: str,
        max_retries: int = 2,
        on_attempt: Optional[Callable[[int, str], None]] = None,
        on_validation: Optional[Callable[[bool, str], None]] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Translate a Datadog dashboard to Grafana format.
        
        Args:
            datadog_dashboard_json: The Datadog dashboard as JSON string
            max_retries: Maximum number of retry attempts
            on_attempt: Callback for each attempt (attempt_num, reasoning)
            on_validation: Callback after validation (success, logs)
        
        Returns:
            (success, data, final_message)
        """
        messages = [
            {"role": "system", "content": DASHBOARD_TRANSLATION_PROMPT},
            {"role": "user", "content": f"Translate this Datadog dashboard to Grafana:\n{datadog_dashboard_json}"}
        ]
        
        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3
                )
                
                content = response.choices[0].message.content
                data = json.loads(content)
                
                if "grafana_dashboard" not in data:
                    raise ValueError("Missing 'grafana_dashboard' in response")
                
                # Notify about reasoning
                if on_attempt:
                    on_attempt(attempt, data.get('reasoning', 'N/A'))
                
                # Validate dashboard schema
                dashboard = data['grafana_dashboard']
                if not isinstance(dashboard, dict):
                    raise ValueError("Dashboard is not a valid JSON object")
                
                valid, logs = validate_grafana_dashboard(dashboard)
                
                # Notify about validation result
                if on_validation:
                    on_validation(valid, logs)
                
                if valid:
                    return True, data, logs
                else:
                    # Self-correction: feed validation errors back to LLM
                    if attempt < max_retries:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": f"""The dashboard failed schema validation with these errors:

{logs}

Fix the errors and regenerate a valid Grafana dashboard. Make sure:
1. All required fields are present (title, panels, etc.)
2. Each panel has: id, type, title, gridPos, targets
3. gridPos includes: x, y, w, h
4. Each target has: expr (or query) and refId
5. Panel IDs are unique integers
6. Queries use valid PromQL syntax"""
                        })
                    else:
                        return False, data, logs
                
            except json.JSONDecodeError as e:
                if attempt == max_retries:
                    return False, None, f"JSON parsing failed: {e}"
            except Exception as e:
                if attempt == max_retries:
                    return False, None, str(e)
        
        return False, None, "Max retries reached"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_agent(api_key: str, model: str) -> MigrationAgent:
    """Factory function to create a configured agent."""
    return MigrationAgent(api_key=api_key, model=model)
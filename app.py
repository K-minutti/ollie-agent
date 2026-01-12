"""
Migration Architect - Streamlit UI

This is just the presentation layer. All the agent logic is in agent.py.
"""

import streamlit as st
import os
import json
from agent import create_agent

# ============================================================================
# UI CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Migration Architect", 
    page_icon="🏗️", 
    layout="wide"
)

st.title("🏗️ Migration Architect: Automated Engineer")
st.markdown("### Watch an AI agent compile and test its own monitoring code")

# ============================================================================
# SIDEBAR CONFIGURATION
# ============================================================================

with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API Key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        api_key = st.text_input("OpenAI API Key", type="password", help="Required for demo")
    
    max_retries = st.slider("Max Retry Attempts", 1, 5, 3)
    
    st.divider()

# ============================================================================
# MODE SELECTION
# ============================================================================

MODE = st.sidebar.radio(
    "Translation Mode",
    ["Queries & Alerts", "Dashboard"],
    help="Choose what to translate"
)

MODEL = st.sidebar.selectbox(
    "AI Model",
    ["gpt-4o", "gpt-5-mini"],
    index=0,
    help="Select the OpenAI model to use"
)

# ============================================================================
# QUERY & ALERT MODE
# ============================================================================

if MODE == "Queries & Alerts":
    st.subheader("📝 Examples")
    
    examples = {
        "CPU Idle (Datadog)": "avg(last_2m):avg:system.cpu.idle{host:*} by {host} < 10",
        "Memory Usage (Datadog)": "avg(last_5m):avg:system.mem.used{*} by {host} / avg:system.mem.total{*} by {host} > 0.9",
        "Error Rate (Datadog)": "sum(last_5m):sum:http.errors{service:api}.as_rate() > 100",
    }
    
    example_choice = st.selectbox("Choose an example or write your own:", ["Custom"] + list(examples.keys()))
    
    if example_choice != "Custom":
        default_query = examples[example_choice]
    else:
        default_query = ""
    
    # Main input
    user_query = st.text_area(
        "Legacy Query (Datadog format)", 
        value=default_query,
        height=100,
        placeholder="e.g., avg(last_5m):avg:system.cpu.idle{host:*} by {host} < 10"
    )
    
    run_button = st.button("🚀 Run Migration Agent", type="primary", disabled=not api_key)
    
    results_placeholder = st.empty()

    if run_button:
        if not user_query.strip():
            st.warning("Please enter a query to migrate")
        else:
            # Clear any previous results
            results_placeholder.empty()
        
            with results_placeholder.container():
                agent = create_agent(api_key)
            
                with st.status("🤖 Agent working...", expanded=True) as status:
                    # Callbacks for progress updates
                    def on_attempt(attempt_num: int, reasoning: str):
                        st.write(f"🔄 **Attempt {attempt_num}/{max_retries}**")
                        st.write(f"💭 **Reasoning**: {reasoning}")
                    
                    def on_validation(valid: bool, logs: str):
                        st.write("🔨 **Compiling and testing...**")
                        if not valid:
                            st.warning("Validation failed, retrying...")
                            with st.expander("🔍 Validation Errors"):
                                st.code(logs, language="text")
                    
                    # Run the agent
                    success, data, logs = agent.translate_query(
                        user_query,
                        max_retries=max_retries,
                        on_attempt=on_attempt,
                        on_validation=on_validation
                    )
                    
                    if success:
                        status.update(label="✅ Migration Complete!", state="complete")
                        st.success("Agent successfully generated and validated the migration!")
                        
                        st.subheader("📦 Generated Artifacts")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("**Rules File** (`rules.yml`)")
                            st.code(data['rule_yaml'], language="yaml", line_numbers=True)
                            st.download_button(
                                "⬇️ Download Rules",
                                data['rule_yaml'],
                                file_name="rules.yml",
                                mime="text/yaml"
                            )
                        
                        with col2:
                            st.markdown("**Test File** (`tests.yml`)")
                            st.code(data['test_yaml'], language="yaml", line_numbers=True)
                            st.download_button(
                                "⬇️ Download Tests",
                                data['test_yaml'],
                                file_name="tests.yml",
                                mime="text/yaml"
                            )
                        
                        st.subheader("🧪 Validation Results")
                        st.code(logs, language="text")
                        
                        # Debug info (collapsible)
                        with st.expander("🔍 Debug: Full Response"):
                            st.json(data)
                        
                    else:
                        status.update(label="❌ Migration Failed", state="error")
                        st.error("Agent could not produce valid output after retries")
                        
                        if logs:
                            st.subheader("🔍 Final Error")
                            st.code(logs, language="text")
                        
                        if data:
                            with st.expander("🐛 Debug: Last Generated Output"):
                                st.json(data)

# ============================================================================
# DASHBOARD MODE
# ============================================================================

else:  # Dashboard mode
    st.info("💡 Upload a Datadog dashboard JSON file or paste it below")
    
    uploaded_file = st.file_uploader("Upload Datadog Dashboard JSON", type=['json'])
    
    if uploaded_file:
        dashboard_json = uploaded_file.read().decode('utf-8')
    else:
        dashboard_json = st.text_area(
            "Or paste Datadog Dashboard JSON",
            height=200,
            placeholder='{"dashboard": {"title": "My Dashboard", ...}}'
        )
    
    run_button = st.button("🚀 Translate Dashboard", type="primary", disabled=not api_key)
    
    results_placeholder = st.empty()
    
    if run_button:
        if not dashboard_json.strip():
            st.warning("Please upload or paste a dashboard JSON")
        else:
            # Clear any previous results
            results_placeholder.empty()

            with results_placeholder.container():
                agent = create_agent(api_key)
            
                with st.status("🤖 Translating dashboard...", expanded=True) as status:
                    # Callbacks for progress updates
                    def on_attempt(attempt_num: int, reasoning: str):
                        st.write(f"🔄 **Attempt {attempt_num}/2**")
                        st.write(f"💭 **Reasoning**: {reasoning}")
                    
                    def on_validation(valid: bool, logs: str):
                        st.write("🔨 **Validating dashboard schema...**")
                        if not valid:
                            st.warning("Schema validation failed, retrying...")
                            with st.expander("🔍 Validation Errors"):
                                st.code(logs, language="text")
                    
                    # Run the agent
                    success, data, logs = agent.translate_dashboard(
                        dashboard_json,
                        max_retries=2,
                        on_attempt=on_attempt,
                        on_validation=on_validation
                    )
                    
                    if success:
                        status.update(label="✅ Dashboard Translated!", state="complete")
                        st.success("Dashboard successfully converted to Grafana format!")
                        
                        st.subheader("📊 Grafana Dashboard JSON")
                        
                        dashboard_str = json.dumps(data['grafana_dashboard'], indent=2)
                        st.code(dashboard_str, language="json", line_numbers=True)
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                                "⬇️ Download Dashboard JSON",
                                dashboard_str,
                                file_name="grafana_dashboard.json",
                                mime="application/json"
                            )
                        with col2:
                            st.info("📌 Import this in Grafana: Dashboards → Import → Upload JSON")
                        
                        # Show validation results
                        st.subheader("🧪 Schema Validation Results")
                        st.code(logs, language="text")
                        
                        st.subheader("🚀 Next Steps")
                        st.markdown("""
                        1. Download the dashboard JSON above
                        2. Open Grafana: http://localhost:3000
                        3. Click **+** → **Import**
                        4. Upload the JSON file
                        5. See your translated queries live!
                        """)
                        
                        # Debug info
                        with st.expander("🔍 Debug: Full Response"):
                            st.json(data)
                    else:
                        status.update(label="❌ Translation Failed", state="error")
                        st.error("Could not translate dashboard")
                        if logs:
                            st.subheader("🔍 Final Error")
                            st.code(logs, language="text")
                        if data:
                            with st.expander("🐛 Debug: Last Generated Output"):
                                st.json(data)

if not api_key:
    st.info("👈 Enter your OpenAI API key in the sidebar to begin")

"""LLM prompts for failure analysis."""

FAILURE_ANALYSIS_PROMPT = """
You are an expert in Istio service mesh troubleshooting.

Analyze the following upgrade failure:
{failure_info}

Logs:
{logs}

Metrics:
{metrics}

Provide a concise root cause analysis and recommended actions.
"""

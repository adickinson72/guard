"""Integration tests for GUARD.

These tests interact with real external services and require:
- Valid AWS credentials
- Access to test AWS resources
- Valid API keys for external services (GitLab, Datadog)

Tests are marked with @pytest.mark.integration and can be run with:
    pytest tests/integration/ -m integration

To skip integration tests:
    pytest -m "not integration"
"""

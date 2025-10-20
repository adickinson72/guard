# Integration Tests

Integration tests verify GUARD's interaction with real external services:
- AWS (STS, EKS, Secrets Manager)
- GitLab (API, repository operations, MR creation)
- Kubernetes (cluster operations, pod management)
- Datadog (metrics querying, monitor management)

## Prerequisites

Integration tests require valid credentials and access to external services. Tests will automatically skip if credentials are not available.

### AWS Integration Tests

**Required:**
- Valid AWS credentials (via `~/.aws/credentials` or environment variables)
- IAM permissions for STS, EKS operations

**Optional Environment Variables:**
```bash
export AWS_TEST_REGION="us-east-1"                          # AWS region for testing
export AWS_TEST_ROLE_ARN="arn:aws:iam::123:role/TestRole" # Role ARN for role assumption tests
```

### GitLab Integration Tests

**Required:**
```bash
export GITLAB_TEST_TOKEN="glpat-xxxxxxxxxxxxx"  # GitLab personal access token
```

**Optional:**
```bash
export GITLAB_TEST_URL="https://gitlab.com"     # GitLab instance URL (default: gitlab.com)
export GITLAB_TEST_PROJECT_ID="group/project"   # Project for read operations
export GITLAB_TEST_ALLOW_WRITE="true"           # Enable write operation tests (branch/MR creation)
```

**Permissions Required:**
- `read_api` (for read-only tests)
- `api` and `write_repository` (for write operation tests)

### Kubernetes Integration Tests

**Required:**
- Valid kubeconfig at `~/.kube/config` or path specified in `KUBECONFIG`
- Access to a Kubernetes cluster

**Optional:**
```bash
export K8S_TEST_CONTEXT="my-test-cluster"       # Specific kubeconfig context to use
export KUBECONFIG="/path/to/kubeconfig"         # Custom kubeconfig path
```

### Datadog Integration Tests

**Required:**
```bash
export DATADOG_TEST_API_KEY="xxxxxxxxxxxxx"     # Datadog API key
export DATADOG_TEST_APP_KEY="xxxxxxxxxxxxx"     # Datadog application key
```

## Running Integration Tests

### Run All Integration Tests
```bash
pytest tests/integration/ -m integration
```

### Run Tests for Specific Client
```bash
# AWS client only
pytest tests/integration/test_aws_client_integration.py

# GitLab client only
pytest tests/integration/test_gitlab_client_integration.py

# Kubernetes client only
pytest tests/integration/test_kubernetes_client_integration.py

# Datadog client only
pytest tests/integration/test_datadog_client_integration.py
```

### Skip Integration Tests
```bash
# Run all tests except integration tests
pytest -m "not integration"

# Run only unit tests
pytest tests/unit/
```

### Skip Slow Tests
Some integration tests are marked as slow (e.g., operations in large clusters):
```bash
# Skip slow integration tests
pytest tests/integration/ -m "integration and not slow"
```

### Run Specific Test Classes
```bash
# Run AWS integration tests only
pytest tests/integration/test_aws_client_integration.py::TestAWSClientIntegration

# Run cross-account tests only
pytest tests/integration/test_aws_client_integration.py::TestAWSClientCrossAccountIntegration
```

## Test Coverage

Integration tests focus on:
1. **Authentication**: Verifying credentials and API access
2. **Read Operations**: Listing, querying, and retrieving resources
3. **Error Handling**: Testing invalid inputs and error responses
4. **Write Operations** (when enabled): Creating branches, files, and MRs (GitLab only)

Integration tests do **not** contribute to code coverage metrics as they test external service interactions rather than code paths.

## CI/CD Integration

In CI/CD pipelines, integration tests should:
1. Be run in a separate stage after unit tests
2. Use service accounts with minimal required permissions
3. Run against dedicated test environments/projects
4. Have longer timeouts than unit tests
5. Be allowed to fail without blocking deployments (flaky external services)

Example CI configuration:
```yaml
integration-tests:
  stage: integration
  script:
    - pytest tests/integration/ -m integration
  only:
    - merge_requests
    - main
  allow_failure: true  # Don't block pipeline on external service issues
  when: manual         # Or run automatically with proper secrets
```

## Writing New Integration Tests

When adding new integration tests:

1. **Use the `@pytest.mark.integration` marker:**
   ```python
   @pytest.mark.integration
   class TestMyClientIntegration:
       ...
   ```

2. **Add skip conditions for missing credentials:**
   ```python
   def test_my_feature(self, skip_if_no_credentials):
       # Test code here
   ```

3. **Test both success and error cases:**
   ```python
   def test_get_resource_success(self, client):
       result = client.get_resource("valid-id")
       assert result is not None

   def test_get_resource_not_found(self, client):
       with pytest.raises(MyError):
           client.get_resource("invalid-id")
   ```

4. **Clean up resources in write tests:**
   ```python
   def test_create_resource(self, client):
       resource = None
       try:
           resource = client.create_resource("test")
           assert resource is not None
       finally:
           if resource:
               client.delete_resource(resource.id)
   ```

5. **Use markers for slow tests:**
   ```python
   @pytest.mark.slow
   def test_large_query(self, client):
       # Test that takes significant time
   ```

## Troubleshooting

### Tests Skip with "Credentials not available"
- Verify environment variables are set correctly
- Check credential files exist and are readable
- Ensure credentials have required permissions

### AWS Tests Fail with "AccessDenied"
- Verify IAM permissions for test user/role
- Check if MFA or additional authentication is required
- Ensure you're testing in the correct region

### Kubernetes Tests Fail with "Forbidden"
- Verify kubeconfig context has sufficient RBAC permissions
- Check if service account has required cluster roles
- Ensure cluster is accessible from test environment

### GitLab Tests Fail with "401 Unauthorized"
- Verify token is valid and not expired
- Check token has required scopes (`read_api`, `api`, `write_repository`)
- Ensure token has access to test project

### Datadog Tests Return Empty Results
- Verify metrics exist in your Datadog account
- Check time range includes data
- Ensure API/App keys have required permissions
- Try querying with Datadog UI first to verify data availability

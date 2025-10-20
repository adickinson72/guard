# GUARD Stub Code Remediation Plan

## Executive Summary

**Analysis Date:** 2025-10-20
**Files Analyzed:** 74 Python files
**Issues Found:** 9 incomplete implementations across 6 files
**Critical Blockers:** 0
**Status:** ✅ Core upgrade workflows are fully functional

---

## Priority Matrix

| Priority | Issues | Effort | Timeline |
|----------|--------|--------|----------|
| **P0 (Critical)** | 0 | - | - |
| **P1 (High)** | 0 | - | - |
| **P2 (Medium)** | 4 | 3-4 days | Sprint 1 |
| **P3 (Low)** | 4 | 1-2 days | Sprint 2 |
| **P4 (Enhancement)** | 1 | 2-3 days | Backlog |

---

## Sprint 1: Medium Priority Issues (P2)

### Issue #1: Incomplete Sidecar Version Validation
**File:** `src/guard/services/istio/checks/sidecar_version.py:63`
**Severity:** P2 - Medium
**Effort:** Medium (4-6 hours)

**Current State:**
```python
for pod in pods:
    has_sidecar = any(cs.get("name") == "istio-proxy" for cs in pod.container_statuses)
    if has_sidecar:
        total_pods_checked += 1
        # In real implementation, would check actual version
        # For now, assume versions match
```

**Problem:**
Check doesn't actually compare sidecar proxy versions against control plane version. Always returns success if sidecars are present.

**Solution:**
1. Extract proxy version from pod container status annotations
2. Get expected version from `cluster.current_istio_version`
3. Compare versions and flag mismatches
4. Report pods with version drift

**Implementation Steps:**
```python
def execute(self, cluster: ClusterConfig) -> CheckResult:
    # Get control plane version
    expected_version = cluster.current_istio_version

    # For each pod with istio-proxy container
    for pod in pods:
        proxy_container = next(
            (c for c in pod.spec.containers if c.name == "istio-proxy"), None
        )
        if proxy_container:
            # Extract version from container image tag
            actual_version = self._extract_version_from_image(proxy_container.image)

            if actual_version != expected_version:
                mismatched_pods.append({
                    "pod": f"{pod.metadata.namespace}/{pod.metadata.name}",
                    "expected": expected_version,
                    "actual": actual_version
                })
```

**Test Requirements:**
- Unit test with mock pods having different proxy versions
- Integration test with real cluster (optional)
- Test cases: matching versions, mismatched versions, missing annotations

**Files to Modify:**
- `src/guard/services/istio/checks/sidecar_version.py`
- `tests/unit/services/istio/checks/test_sidecar_version.py` (enhance)

---

### Issue #2: Missing Istio Deployment Validation
**File:** `src/guard/validation/engine.py:157`
**Severity:** P2 - Medium
**Effort:** Medium (3-4 hours)

**Current State:**
```python
def validate_istio_deployment(self, cluster: ClusterConfig) -> CheckResult:
    logger.info("validating_istio_deployment", cluster_id=cluster.cluster_id)
    # TODO: Implement Istio deployment validation
    return CheckResult(
        check_name="istio_deployment",
        passed=True,
        message="Istio deployment validated",
        timestamp=datetime.utcnow(),
    )
```

**Problem:**
Always returns success without any actual validation of Istio control plane state.

**Solution:**
Validate Istio control plane components are healthy:
1. Check istiod deployment is ready
2. Verify revision labels match expected version
3. Validate control plane pods are running
4. Confirm service endpoints are available

**Implementation Steps:**
```python
def validate_istio_deployment(self, cluster: ClusterConfig) -> CheckResult:
    issues = []

    # 1. Check istiod deployment
    try:
        istiod = self.k8s_client.get_deployment("istiod", "istio-system")
        if not istiod or istiod.status.available_replicas < 1:
            issues.append("istiod deployment not ready")
    except Exception as e:
        issues.append(f"Failed to get istiod: {e}")

    # 2. Verify revision label
    expected_revision = f"istio-{cluster.current_istio_version}"
    actual_revision = istiod.metadata.labels.get("istio.io/rev")
    if actual_revision != expected_revision:
        issues.append(f"Revision mismatch: {actual_revision} != {expected_revision}")

    # 3. Check control plane pods
    pods = self.k8s_client.list_pods(
        namespace="istio-system",
        label_selector="app=istiod"
    )
    ready_pods = [p for p in pods if p.status.phase == "Running"]
    if len(ready_pods) < 1:
        issues.append("No running istiod pods found")

    passed = len(issues) == 0
    return CheckResult(...)
```

**Test Requirements:**
- Mock kubernetes client with various deployment states
- Test healthy deployment returns success
- Test missing deployment returns failure
- Test wrong revision returns failure

**Files to Modify:**
- `src/guard/validation/engine.py`
- `tests/unit/validation/test_engine.py`

---

### Issue #3: Incomplete StatefulSet/DaemonSet Readiness Checks
**File:** `src/guard/validation/engine.py:363`
**Severity:** P2 - Medium
**Effort:** Medium (4-5 hours)

**Current State:**
```python
for kind, ns, name in wave_restarted:
    try:
        if kind == "Deployment":
            if k8s_client.check_deployment_ready(name=name, namespace=ns):
                ready_count += 1
        # Note: StatefulSets and DaemonSets need similar ready checks
        # For now, we assume they're ready if no error
        else:
            ready_count += 1
```

**Problem:**
StatefulSets and DaemonSets don't get proper readiness validation. Code assumes they're ready if no exception is thrown.

**Solution:**
Implement proper readiness checks for all workload types.

**Implementation Steps:**

1. **Add methods to KubernetesClient:**
```python
# In src/guard/clients/kubernetes_client.py

def check_statefulset_ready(self, name: str, namespace: str) -> bool:
    """Check if StatefulSet is ready."""
    sts = self.apps_v1.read_namespaced_stateful_set(name, namespace)

    # Check if all replicas are ready
    if sts.spec.replicas != sts.status.ready_replicas:
        return False

    # Check if currentReplicas matches replicas
    if sts.status.current_replicas != sts.spec.replicas:
        return False

    # Check if update is complete
    if sts.status.current_revision != sts.status.update_revision:
        return False

    return True

def check_daemonset_ready(self, name: str, namespace: str) -> bool:
    """Check if DaemonSet is ready."""
    ds = self.apps_v1.read_namespaced_daemon_set(name, namespace)

    # Check if all desired pods are ready
    if ds.status.desired_number_scheduled != ds.status.number_ready:
        return False

    # Check if no pods are unavailable
    if ds.status.number_unavailable and ds.status.number_unavailable > 0:
        return False

    return True
```

2. **Update validation engine:**
```python
# In src/guard/validation/engine.py

for kind, ns, name in wave_restarted:
    try:
        if kind == "Deployment":
            if k8s_client.check_deployment_ready(name=name, namespace=ns):
                ready_count += 1
        elif kind == "StatefulSet":
            if k8s_client.check_statefulset_ready(name=name, namespace=ns):
                ready_count += 1
        elif kind == "DaemonSet":
            if k8s_client.check_daemonset_ready(name=name, namespace=ns):
                ready_count += 1
    except Exception as e:
        logger.debug("readiness_check_failed", ...)
```

**Test Requirements:**
- Unit tests for each new readiness check method
- Mock StatefulSet/DaemonSet with various states (ready, updating, not ready)
- Integration test with validation engine

**Files to Modify:**
- `src/guard/clients/kubernetes_client.py`
- `src/guard/validation/engine.py`
- `tests/unit/clients/test_kubernetes_client.py`
- `tests/unit/validation/test_engine.py`

---

## Sprint 2: Low Priority Issues (P3)

### Issue #3.5: IGU to GUARD Naming Cleanup
**Multiple Files**
**Severity:** P2 - Medium
**Effort:** Medium (3-4 hours)

**Current State:**
Many files still contain references to "igu" (old name) instead of "guard" (new name). While the core Python package was renamed, documentation, scripts, configuration examples, and comments still use the old name.

**Problem:**
Inconsistent naming causes confusion and may break user workflows expecting "guard" everywhere.

**Affected Areas:**
1. **Scripts:** `scripts/bootstrap.sh` - Uses `~/.igu/` directory
2. **.gitignore:** References `.igu/` directories
3. **Documentation:** Multiple docs files reference `igu` command
4. **Configuration Examples:** `examples/config.yaml.example` uses `igu/` secret paths
5. **Code Comments:** `src/guard/__main__.py`, `src/guard/clients/aws_client.py`
6. **Kubernetes Examples:** `CLAUDE.md` line 71 has kubectl example with `igu`

**Solution:**
Systematic rename of all remaining "igu" references to "guard":

1. **Configuration paths:** `~/.igu/` → `~/.guard/`
2. **Secret names:** `igu/gitlab-token` → `guard/gitlab-token`
3. **CLI commands:** `igu run` → `guard run`
4. **Session names:** `igu-session` → `guard-session`
5. **AWS resources:** `igu-prod` → `guard-prod`

**Implementation Steps:**

```bash
# 1. Update all documentation
find docs/ -type f -name "*.md" -exec sed -i '' 's/\bigu\b/guard/g' {} \;
find docs/ -type f -name "*.md" -exec sed -i '' 's/IGU/GUARD/g' {} \;

# 2. Update examples
find examples/ -type f -exec sed -i '' 's/\bigu\b/guard/g' {} \;
find examples/ -type f -exec sed -i '' 's/IGU/GUARD/g' {} \;

# 3. Update scripts
sed -i '' 's/\.igu/\.guard/g' scripts/bootstrap.sh
sed -i '' 's/IGU/GUARD/g' scripts/bootstrap.sh

# 4. Update .gitignore
sed -i '' 's/\.igu/\.guard/g' .gitignore
sed -i '' 's/IGU/GUARD/g' .gitignore

# 5. Update code comments
find src/ -type f -name "*.py" -exec sed -i '' 's/IGU-/GUARD-/g' {} \;

# 6. Update CLAUDE.md
sed -i '' 's/igu run/guard run/g' CLAUDE.md

# 7. Update plan.md
sed -i '' 's/\bigu\b/guard/g' plan.md
```

**Manual Review Required:**
Some references may need contextual changes:
- AWS Secret Manager paths (coordinate with ops team)
- Existing user configurations (backward compatibility)
- IAM role names (may require terraform updates)

**Backward Compatibility Strategy:**
For paths and configs that users may have customized:

```python
# In src/guard/core/config.py
def get_config_path() -> Path:
    """Get config directory, checking both new and legacy paths."""
    new_path = Path.home() / ".guard"
    legacy_path = Path.home() / ".igu"

    # Check legacy path first for backward compatibility
    if legacy_path.exists() and not new_path.exists():
        warnings.warn(
            "Using legacy config path ~/.igu/. "
            "Please migrate to ~/.guard/ for future versions.",
            DeprecationWarning,
            stacklevel=2
        )
        return legacy_path

    return new_path
```

**Test Requirements:**
- Verify all documentation examples work with new naming
- Test bootstrap script creates `~/.guard/` directory
- Confirm CLI commands work: `guard run`, `guard monitor`, etc.
- Check for any missed references: `grep -r "igu" --exclude-dir=.git`

**Files to Modify:**
- `scripts/bootstrap.sh`
- `.gitignore`
- All files in `docs/` directory
- All files in `examples/` directory
- `CLAUDE.md`
- `plan.md`
- `src/guard/core/config.py` (add backward compatibility)

---

### Issue #4: Missing Flux Config Update in Legacy GitOps Manager
**File:** `src/guard/gitops/manager.py:49`
**Severity:** P3 - Low
**Effort:** Low (1-2 hours)

**Current State:**
```python
def create_upgrade_mr(self, cluster, target_version, pre_check_results):
    # TODO: Implement Flux config update

    # Create MR
    mr = self.gitlab.create_merge_request(...)
```

**Problem:**
Function doesn't update Flux HelmRelease YAML files.

**Solution:**
⚠️ **RECOMMENDATION: Deprecate this file instead of completing it.**

This is legacy code. The primary implementation in `gitops/gitops_orchestrator.py` is complete and handles Flux updates properly. This file should be:
1. Marked as deprecated with clear docstring
2. Add deprecation warning when used
3. Update documentation to use `GitopsOrchestrator` instead

**Implementation:**
```python
import warnings

class GitopsManager:
    """
    DEPRECATED: Use GitopsOrchestrator instead.

    This class is a legacy implementation and will be removed in a future version.
    For new code, use src.guard.gitops.gitops_orchestrator.GitopsOrchestrator.
    """

    def __init__(self, ...):
        warnings.warn(
            "GitopsManager is deprecated. Use GitopsOrchestrator instead.",
            DeprecationWarning,
            stacklevel=2
        )
```

**Files to Modify:**
- `src/guard/gitops/manager.py`
- Documentation/CLAUDE.md (note deprecation)

---

### Issue #5: Legacy Metrics Comparator
**File:** `src/guard/validation/metrics_comparator.py:34`
**Severity:** P3 - Low
**Effort:** Low (1 hour)

**Current State:**
```python
def compare_metrics(self, baseline: dict, current: dict):
    logger.info("comparing_metrics")
    issues = []

    # TODO: Implement actual metric comparison logic
    # Check latency, error rate, resource usage, etc.

    passed = len(issues) == 0
    return passed, issues
```

**Problem:**
Always returns success without comparing metrics.

**Solution:**
⚠️ **RECOMMENDATION: Deprecate this file instead of completing it.**

This is superseded by:
- `validation/validation_orchestrator.py` - Comprehensive validation framework
- `services/istio/validators/latency.py` - IstioLatencyValidator
- `services/istio/validators/error_rate.py` - IstioErrorRateValidator

**Implementation:**
```python
import warnings

class MetricsComparator:
    """
    DEPRECATED: Use validation_orchestrator.py with specific validators instead.

    This class is superseded by:
    - validation.validation_orchestrator.ValidationOrchestrator
    - services.istio.validators.latency.IstioLatencyValidator
    - services.istio.validators.error_rate.IstioErrorRateValidator
    """

    def __init__(self, ...):
        warnings.warn(
            "MetricsComparator is deprecated. Use ValidationOrchestrator with "
            "specific validators instead.",
            DeprecationWarning,
            stacklevel=2
        )
```

**Files to Modify:**
- `src/guard/validation/metrics_comparator.py`
- Remove imports from other files if present

---

### Issue #6: Missing User Lookup in GitOps Orchestrator
**File:** `src/guard/gitops/gitops_orchestrator.py:168`
**Severity:** P3 - Low
**Effort:** Low (2-3 hours)

**Current State:**
```python
# Parse assignee from owner_handle if available
assignee_ids = None
if cluster.owner_handle:
    # Would need to look up user ID from handle
    # For now, skip assignee
    pass
```

**Problem:**
MRs are created without auto-assigning to cluster owner.

**Solution:**
Implement GitLab user lookup by handle.

**Implementation Steps:**

1. **Add method to GitLabClient:**
```python
# In src/guard/clients/gitlab_client.py

def get_user_id_by_username(self, username: str) -> int | None:
    """
    Look up GitLab user ID by username.

    Args:
        username: GitLab username (handle without @)

    Returns:
        User ID if found, None otherwise
    """
    try:
        users = self.gl.users.list(username=username)
        if users:
            return users[0].id
        return None
    except Exception as e:
        logger.warning("user_lookup_failed", username=username, error=str(e))
        return None
```

2. **Update GitopsOrchestrator:**
```python
# In src/guard/gitops/gitops_orchestrator.py

# Parse assignee from owner_handle if available
assignee_ids = None
if cluster.owner_handle:
    # Remove @ prefix if present
    username = cluster.owner_handle.lstrip("@")
    user_id = self.gitlab_client.get_user_id_by_username(username)
    if user_id:
        assignee_ids = [user_id]
        logger.info("mr_assignee_set", username=username, user_id=user_id)
    else:
        logger.warning("user_not_found", username=username)
```

**Test Requirements:**
- Mock GitLab API user lookup
- Test successful lookup
- Test user not found
- Test with/without @ prefix

**Files to Modify:**
- `src/guard/clients/gitlab_client.py`
- `src/guard/gitops/gitops_orchestrator.py`
- `tests/unit/clients/test_gitlab_client.py`
- `tests/unit/gitops/test_gitops_orchestrator.py`

---

### Issue #7: Incomplete TODO Comment Cleanup
**Severity:** P3 - Low
**Effort:** Low (30 minutes)

**Files with TODO Comments:**
After implementing the above issues, search and remove obsolete TODO comments:
- `src/guard/gitops/manager.py:49`
- `src/guard/validation/metrics_comparator.py:34`
- `src/guard/validation/engine.py:157`
- `src/guard/validation/engine.py:363`
- `src/guard/services/istio/checks/sidecar_version.py:63`

**Implementation:**
```bash
# Search for remaining TODOs
grep -rn "TODO" src/guard/

# Review each TODO and either:
# 1. Implement the functionality
# 2. Convert to GitHub issue if deferred
# 3. Remove if obsolete
```

---

## Backlog: Enhancement Issues (P4)

### Issue #8: LLM-Based Failure Analysis
**File:** `src/guard/llm/analyzer.py:40`
**Severity:** P4 - Enhancement
**Effort:** Medium-High (6-8 hours)

**Current State:**
```python
def analyze_failure(self, failure_data, logs=None, metrics=None):
    logger.info("analyzing_failure")

    # TODO: Implement LLM-based failure analysis
    analysis = "Failure analysis placeholder"

    logger.info("failure_analysis_completed")
    return analysis
```

**Problem:**
Returns hardcoded placeholder instead of using LLM for root cause analysis.

**Solution:**
Implement OpenAI integration for failure analysis.

**Implementation Steps:**

1. **Add OpenAI client dependency:**
```bash
poetry add openai
```

2. **Implement LLM analyzer:**
```python
from openai import OpenAI
from .prompts import FAILURE_ANALYSIS_PROMPT

class LLMFailureAnalyzer:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4"  # or gpt-3.5-turbo for cost savings

    def analyze_failure(
        self,
        failure_data: dict,
        logs: str | None = None,
        metrics: dict | None = None
    ) -> str:
        """Use LLM to analyze upgrade failure and suggest root cause."""

        # Build context from failure data
        context = self._build_context(failure_data, logs, metrics)

        # Call OpenAI API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": FAILURE_ANALYSIS_PROMPT},
                {"role": "user", "content": context}
            ],
            temperature=0.3,  # Lower for more deterministic analysis
            max_tokens=1000
        )

        analysis = response.choices[0].message.content

        logger.info("llm_analysis_completed",
                   tokens_used=response.usage.total_tokens)

        return analysis

    def _build_context(self, failure_data, logs, metrics) -> str:
        """Build analysis context from available data."""
        parts = [
            "# Upgrade Failure Analysis Request",
            f"\n## Cluster: {failure_data.get('cluster_id')}",
            f"## Target Version: {failure_data.get('target_version')}",
            f"## Failure Type: {failure_data.get('failure_type')}",
            f"## Error Message: {failure_data.get('error_message')}",
        ]

        if logs:
            parts.append(f"\n## Recent Logs:\n```\n{logs[:5000]}\n```")

        if metrics:
            parts.append(f"\n## Metrics Data:\n{json.dumps(metrics, indent=2)}")

        return "\n".join(parts)
```

3. **Update prompts.py:**
```python
FAILURE_ANALYSIS_PROMPT = """
You are an expert Kubernetes and Istio upgrade troubleshooter.
Analyze the provided upgrade failure data and provide:

1. Most likely root cause
2. Supporting evidence from logs/metrics
3. Recommended remediation steps
4. Whether rollback is necessary

Be concise and focus on actionable insights.
"""
```

4. **Add configuration:**
```python
# In core/config.py
class LLMConfig(BaseModel):
    enabled: bool = False
    provider: str = "openai"  # Future: support anthropic, etc.
    api_key: str | None = None  # Or fetch from AWS Secrets Manager
    model: str = "gpt-4"
```

**Test Requirements:**
- Mock OpenAI API responses
- Test with various failure scenarios
- Test token limit handling
- Cost estimation tests

**Files to Modify:**
- `src/guard/llm/analyzer.py`
- `src/guard/llm/prompts.py`
- `src/guard/core/config.py`
- `tests/unit/llm/test_analyzer.py`

**Considerations:**
- Add cost limits/budgets
- Implement caching for similar failures
- Add telemetry for analysis quality feedback
- Consider data privacy for logs sent to OpenAI

---

## Implementation Timeline

```
Week 1 (Sprint 1 - P2 Issues):
├── Day 1-2: Issue #1 (Sidecar version validation)
├── Day 2-3: Issue #2 (Istio deployment validation)
├── Day 3-4: Issue #3 (StatefulSet/DaemonSet readiness)
└── Day 4-5: Issue #3.5 (IGU to GUARD naming cleanup)

Week 2 (Sprint 2 - P3 Issues):
├── Day 1: Issue #4 (Deprecate legacy GitOps manager)
├── Day 1: Issue #5 (Deprecate legacy metrics comparator)
├── Day 2: Issue #6 (User lookup for MR assignment)
└── Day 2: Issue #7 (TODO cleanup)

Backlog (Future Sprint):
└── Issue #8 (LLM failure analysis) - Enhancement feature
```

---

## Testing Strategy

### Unit Tests (Required)
- All new methods must have 90%+ coverage
- Use pytest fixtures from `tests/conftest.py`
- Mock external dependencies (K8s API, GitLab API, OpenAI)

### Integration Tests (Recommended)
- Test against real Kubernetes cluster (optional, local)
- Validate StatefulSet/DaemonSet restart behavior
- Test MR creation with real GitLab instance (staging)

### E2E Tests (Optional)
- Full upgrade workflow with test cluster
- Validate sidecar version checking in real environment

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| StatefulSet restart causes data loss | Low | High | Add volume mount validation before restart |
| Version comparison logic breaks with beta/rc versions | Medium | Medium | Add comprehensive version parsing tests |
| GitLab user lookup fails for federated users | Low | Low | Gracefully degrade to no assignee |
| LLM API costs exceed budget | Medium | Low | Implement rate limiting and cost caps |

---

## Success Criteria

### Sprint 1 (P2)
- ✅ All sidecar version mismatches are detected and reported
- ✅ Istio control plane validation catches unhealthy deployments
- ✅ StatefulSet/DaemonSet restarts are validated for readiness
- ✅ All "igu" references renamed to "guard" with backward compatibility

### Sprint 2 (P3)
- ✅ Legacy code properly deprecated with warnings
- ✅ MRs automatically assigned to cluster owners
- ✅ Zero TODO comments in production code

### Backlog (P4)
- ✅ LLM provides actionable failure analysis
- ✅ Analysis cost <$1 per failure
- ✅ Analysis quality validated by operators

---

## Rollout Plan

1. **Development:**
   - Create feature branch: `feature/stub-code-remediation`
   - Implement changes incrementally with tests
   - Ensure 90%+ test coverage maintained

2. **Testing:**
   - Run full test suite: `pytest --cov=guard --cov-report=html`
   - Manual testing against dev cluster
   - Peer review all changes

3. **Deployment:**
   - Create GitLab MR with this plan attached
   - Get approval from at least 2 reviewers
   - Merge to main after CI passes
   - Deploy to test environment first
   - Monitor for 48 hours before prod rollout

4. **Validation:**
   - Run upgrade against test batch
   - Verify new validation checks work
   - Confirm deprecated code warnings appear
   - Check logs for any regressions

---

## Appendix

### File Reference Map

```
P2 Issues (Critical Path):
├── src/guard/services/istio/checks/sidecar_version.py
├── src/guard/validation/engine.py
├── src/guard/clients/kubernetes_client.py
└── Naming Cleanup (Issue #3.5):
    ├── scripts/bootstrap.sh
    ├── .gitignore
    ├── CLAUDE.md
    ├── plan.md
    ├── docs/** (all markdown files)
    ├── examples/** (all config files)
    └── src/guard/core/config.py (backward compatibility)

P3 Issues (Nice-to-Have):
├── src/guard/gitops/manager.py (deprecate)
├── src/guard/validation/metrics_comparator.py (deprecate)
├── src/guard/clients/gitlab_client.py
└── src/guard/gitops/gitops_orchestrator.py

P4 Issues (Enhancement):
├── src/guard/llm/analyzer.py
├── src/guard/llm/prompts.py
└── src/guard/core/config.py
```

### Related Documentation
- Main project docs: `/Users/adickinson/repos/guard/CLAUDE.md`
- Test strategy: `tests/README.md` (if exists)
- Architecture: See CLAUDE.md "Architecture" section

---

## Questions for Team Discussion

1. **LLM Integration:** Should we prioritize LLM failure analysis or defer to backlog?
2. **Legacy Code:** Should deprecated files be removed entirely or kept with warnings?
3. **StatefulSet Safety:** Do we need additional safeguards for StatefulSet restarts?
4. **Cost:** What's the acceptable cost per LLM analysis call?
5. **Testing:** Should we require integration tests against real clusters?

---

**Document Version:** 1.0
**Last Updated:** 2025-10-20
**Author:** Generated by Claude Code (Systematic Codebase Analysis)
**Review Required:** Yes - Team review recommended before implementation

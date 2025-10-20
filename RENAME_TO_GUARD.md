# Rename Project: GUARD → GUARD

## Overview

Rename the project from **GUARD (GitOps Upgrade Automation with Rollback Detection)** to **GUARD (GitOps Upgrade Automation with Rollback Detection)** to reflect its broader scope beyond Istio.

**New Identity:**
- **Name:** GUARD
- **Full Name:** GitOps Upgrade Automation with Rollback Detection
- **Tagline:** "Protecting your GitOps deployments with intelligent automation"

---

## 1. Repository & GitLab Setup

### 1.1 Rename GitLab Repository
- Rename repository from `igu` to `guard` in GitLab settings
- Update repository slug and URL
- Update any repository webhooks or integrations

### 1.2 Update Remote URL Locally
```bash
git remote set-url origin <new-guard-url>
```

---

## 2. Python Package Renaming

### 2.1 Directory Structure
```bash
# Rename the main source directory
mv src/igu src/guard
```

### 2.2 Update pyproject.toml

Changes needed:
- Package name: `name = "igu"` → `name = "guard"`
- Description: Update to remove Istio-specific language
  - Old: "GitOps Upgrade Automation with Rollback Detection - Automate safe, progressive Istio upgrades across multiple EKS clusters"
  - New: "GUARD - GitOps Upgrade Automation with Rollback Detection for Kubernetes services"
- Homepage: `https://github.com/your-org/igu` → `https://github.com/your-org/guard`
- Repository: `https://github.com/your-org/igu` → `https://github.com/your-org/guard`
- Documentation: `https://github.com/your-org/igu/docs` → `https://github.com/your-org/guard/docs`
- Keywords: `["istio", "kubernetes", "eks", "gitops", "automation"]` → `["gitops", "kubernetes", "eks", "automation", "upgrades", "deployment", "rollback"]`
- Packages: `packages = [{include = "igu", from = "src"}]` → `packages = [{include = "guard", from = "src"}]`
- Scripts: `igu = "igu.cli.main:cli"` → `guard = "guard.cli.main:cli"`
- isort config: `known-first-party = ["igu"]` → `known-first-party = ["guard"]`
- pytest coverage: `--cov=igu` → `--cov=guard`
- Coverage source: `source = ["src/igu"]` → `source = ["src/guard"]`

### 2.3 Update All Python Import Statements

**Files requiring updates:** All 76 `.py` files in `src/` and `tests/`

Find and replace:
- `from igu.` → `from guard.`
- `import igu.` → `import guard.`
- `from igu ` → `from guard `

Can be done with:
```bash
# Find all Python files with igu imports
rg "from igu\.|import igu\." --type py -l

# Use sed or your editor to replace
find src tests -name "*.py" -exec sed -i '' 's/from igu\./from guard./g' {} +
find src tests -name "*.py" -exec sed -i '' 's/import igu\./import guard./g' {} +
```

---

## 3. Documentation Updates

### 3.1 README.md

Major changes:
- Title: `# GitOps Upgrade Automation with Rollback Detection (GUARD)` → `# GUARD - GitOps Upgrade Automation with Rollback Detection`
- Subtitle: Update to reflect generic service upgrades
- Badge URLs: Update GitHub URLs
- Overview: Rewrite to be service-agnostic
- Installation: `pip install igu` → `pip install guard`
- CLI examples: `igu` → `guard` (all command examples)
- Docker image: `<registry>/igu:latest` → `<registry>/guard:latest`
- Config path: `~/.guard/config.yaml` → `~/.guard/config.yaml`
- Namespace: `kubectl exec -n igu-system` → `kubectl exec -n guard-system`
- Secrets: `igu/gitlab-token` → `guard/gitlab-token`
- Script: `./scripts/setup-dynamodb.sh` references
- Project structure: `igu/` → `guard/`
- Repository URLs throughout
- Anchor links: `#istio-gitops-upgrader-igu` → `#guard`

### 3.2 All Documentation Files

**Files to update:**
1. CHANGELOG.md - Update project name, add rename note
2. CLAUDE.md - Update any GUARD references
3. BLACK_BOX_DESIGN_PROMPT.md - Update project name
4. REFACTORING_SUMMARY.md - Update project name
5. docs/architecture.md - Update diagrams, CLI references, package names
6. docs/api-reference.md - Update module names
7. docs/configuration.md - Update config paths, examples
8. docs/contributing.md - Update repo URLs, package names
9. docs/examples/advanced-scenarios.md - Update CLI commands
10. docs/examples/basic-usage.md - Update CLI commands
11. docs/examples/troubleshooting.md - Update CLI commands
12. docs/security.md - Update secrets paths, IAM role references
13. docs/testing.md - Update import examples
14. docs/getting-started.md - Update installation, CLI commands
15. docs/extensibility.md - Update package references
16. docs/kubernetes-deployment.md - Update namespace, deployments
17. docs/architecture/interfaces.md - Update module paths
18. docs/architecture/black-box-design.md - Update project name
19. k8s/README.md - Update namespace, deployment references

**Global replacements:**
- CLI command: `igu` → `guard`
- Package name: `igu.` → `guard.`
- Config directory: `~/.guard/` → `~/.guard/`
- Namespace: `igu-system` → `guard-system`
- Repository URLs
- Project name: GUARD → GUARD
- Full name: GitOps Upgrade Automation with Rollback Detection → GitOps Upgrade Automation with Rollback Detection

---

## 4. Kubernetes Manifests

### 4.1 k8s/namespace.yaml
```yaml
# Change namespace name
name: igu-system → guard-system
labels:
  name: igu-system → guard-system
  app.kubernetes.io/name: igu → guard
```

### 4.2 k8s/deployment.yaml
- Namespace: `igu-system` → `guard-system`
- Deployment name: `igu` → `guard`
- Labels: `app: igu` → `app: guard`
- Service account: `igu` → `guard`
- Container name: `igu` → `guard`
- Image: `<registry>/igu:*` → `<registry>/guard:*`
- Volume mounts: `.igu` → `.guard`

### 4.3 k8s/configmap.yaml
- Namespace: `igu-system` → `guard-system`
- ConfigMap name: `igu-config` → `guard-config`
- Labels: `app: igu` → `app: guard`

### 4.4 k8s/serviceaccount.yaml
- Namespace: `igu-system` → `guard-system`
- ServiceAccount name: `igu` → `guard`
- Labels: `app: igu` → `app: guard`

### 4.5 k8s/rbac.yaml
- Namespace: `igu-system` → `guard-system`
- Role name: `igu` → `guard`
- RoleBinding name: `igu` → `guard`
- ServiceAccount reference: `igu` → `guard`
- Labels: `app: igu` → `app: guard`

### 4.6 k8s/cronjob.yaml
- Namespace: `igu-system` → `guard-system`
- CronJob name: `igu-*` → `guard-*`
- Labels: `app: igu` → `app: guard`
- Service account: `igu` → `guard`
- Image: `<registry>/igu:*` → `<registry>/guard:*`

### 4.7 k8s/kustomization.yaml
- Namespace: `igu-system` → `guard-system`
- commonLabels: `app: igu` → `app: guard`

---

## 5. Docker Configuration

### 5.1 Dockerfile

Changes:
```dockerfile
# Line 33: Update user creation
RUN useradd -m -u 1000 -s /bin/bash igu
→
RUN useradd -m -u 1000 -s /bin/bash guard

# Line 52: Update ownership
RUN chown -R igu:igu /app
→
RUN chown -R guard:guard /app

# Line 55: Update user
USER igu
→
USER guard

# Line 58: Update entrypoint
ENTRYPOINT ["igu"]
→
ENTRYPOINT ["guard"]
```

### 5.2 Docker Build Commands

Update in documentation:
```bash
# Old
docker build -t <YOUR_REGISTRY>/igu:latest .
docker push <YOUR_REGISTRY>/igu:latest

# New
docker build -t <YOUR_REGISTRY>/guard:latest .
docker push <YOUR_REGISTRY>/guard:latest
```

---

## 6. Scripts

### 6.1 scripts/setup-dynamodb.sh

Changes:
```bash
# Line 6: Update default table name
TABLE_NAME="${1:-igu-cluster-registry}"
→
TABLE_NAME="${1:-guard-cluster-registry}"

# Line 4: Update comments
# Setup DynamoDB tables for GUARD
→
# Setup DynamoDB tables for GUARD

# Line 30: Update locks table name in echo
echo "  aws dynamodb create-table --table-name igu-locks \\"
→
echo "  aws dynamodb create-table --table-name guard-locks \\"
```

### 6.2 scripts/bootstrap.sh

Review and update any GUARD references if present.

---

## 7. Configuration & Examples

### 7.1 Configuration Paths

Update references:
- Config directory: `~/.guard/` → `~/.guard/`
- AWS Secrets Manager:
  - `igu/gitlab-token` → `guard/gitlab-token`
  - `igu/datadog-credentials` → `guard/datadog-credentials`
- DynamoDB tables:
  - `igu-cluster-registry` → `guard-cluster-registry`
  - `igu-locks` → `guard-locks`

### 7.2 Environment Variables

If any exist, rename:
- `GUARD_*` → `GUARD_*`

### 7.3 Example Files

Update any files in `examples/` directory with:
- Config paths
- CLI commands
- Table names
- Package imports

---

## 8. Testing Configuration

### 8.1 pyproject.toml Test Config

Already covered in section 2.2, but specifically:
```toml
[tool.pytest.ini_options]
addopts = [
    "--cov=igu",  # → "--cov=guard"
]

[tool.coverage.run]
source = ["src/igu"]  # → source = ["src/guard"]
```

### 8.2 Test Files

Update all test files:
- Import statements: `from igu.` → `from guard.`
- Any hardcoded strings referencing "igu"
- Mock paths if any reference the package name

---

## 9. Additional Files

### 9.1 Git Configuration

Create a tag for the last GUARD version:
```bash
git tag -a v0.1.0-igu -m "Last version as GUARD before rename to GUARD"
git push origin v0.1.0-igu
```

Update version:
```toml
# pyproject.toml
version = "0.1.0"  # → "0.2.0"
```

### 9.2 CHANGELOG.md

Add entry:
```markdown
## [0.2.0] - 2025-01-XX

### Changed
- **BREAKING:** Project renamed from GUARD (GitOps Upgrade Automation with Rollback Detection) to GUARD (GitOps Upgrade Automation with Rollback Detection)
- CLI command changed from `igu` to `guard`
- Python package renamed from `igu` to `guard`
- Kubernetes namespace changed from `igu-system` to `guard-system`
- Config directory changed from `~/.guard/` to `~/.guard/`
- All documentation updated to reflect new name and broader scope

### Migration Guide
- Reinstall package: `pip uninstall igu && pip install guard`
- Update CLI commands: `igu` → `guard`
- Rename config directory: `mv ~/.guard ~/.guard`
- Update Kubernetes resources: `kubectl delete ns igu-system && kubectl apply -k k8s/`
- Update AWS Secrets Manager paths (optional, old paths still work)
- Update DynamoDB table names (optional, old tables can coexist)
```

### 9.3 CI/CD Pipeline

If GitLab CI/CD exists:
- Update Docker image tags
- Update deployment scripts
- Update any hardcoded references to `igu`

---

## 10. Execution Checklist

### Phase 1: Repository Setup
- [ ] Create git tag `v0.1.0-igu`
- [ ] Rename GitLab repository to `guard`
- [ ] Update local git remote URL

### Phase 2: Code Changes
- [ ] Rename `src/igu/` to `src/guard/`
- [ ] Update pyproject.toml (all references)
- [ ] Update all Python import statements (76 files)
- [ ] Update Dockerfile
- [ ] Update all shell scripts

### Phase 3: Kubernetes
- [ ] Update namespace.yaml
- [ ] Update deployment.yaml
- [ ] Update configmap.yaml
- [ ] Update serviceaccount.yaml
- [ ] Update rbac.yaml
- [ ] Update cronjob.yaml
- [ ] Update kustomization.yaml

### Phase 4: Documentation
- [ ] Update README.md
- [ ] Update CHANGELOG.md
- [ ] Update all docs/*.md files (15+ files)
- [ ] Update k8s/README.md
- [ ] Update CLAUDE.md

### Phase 5: Configuration
- [ ] Update example config files
- [ ] Document migration path for users
- [ ] Update AWS resource names (optional)

### Phase 6: Testing
- [ ] Run all tests: `pytest`
- [ ] Test CLI command: `guard --help`
- [ ] Build Docker image: `docker build -t guard:test .`
- [ ] Validate K8s manifests: `kubectl apply --dry-run=client -k k8s/`
- [ ] Check for remaining "igu" references: `rg -i "\\bigu\\b" --type-not md`

### Phase 7: Deployment
- [ ] Build and push new Docker image
- [ ] Deploy to test environment
- [ ] Validate functionality
- [ ] Update production deployments

---

## 11. Search & Replace Commands

### Find all references
```bash
# Case-insensitive search for "igu" (word boundary)
rg -i "\\bigu\\b" --type-not md

# Find in Python files
rg "from igu\.|import igu\." --type py

# Find in YAML files
rg "igu" --type yaml

# Find in Markdown files
rg "igu" --type md
```

### Automated replacements (use with caution)
```bash
# Python imports
find src tests -name "*.py" -exec sed -i '' 's/from igu\./from guard./g' {} +
find src tests -name "*.py" -exec sed -i '' 's/import igu\./import guard./g' {} +

# YAML files
find k8s -name "*.yaml" -exec sed -i '' 's/igu-system/guard-system/g' {} +
find k8s -name "*.yaml" -exec sed -i '' 's/app: igu/app: guard/g' {} +

# Documentation (review changes manually first!)
find docs -name "*.md" -exec sed -i '' 's/\bigu\b/guard/g' {} +
```

---

## 12. Verification Tests

After completing the rename:

### 12.1 Python Package
```bash
# Install in development mode
poetry install

# Verify CLI works
guard --help
guard --version

# Run all tests
poetry run pytest

# Run linting
poetry run ruff check .
poetry run mypy src/
```

### 12.2 Docker
```bash
# Build image
docker build -t guard:test .

# Run container
docker run --rm guard:test --help

# Verify entrypoint
docker inspect guard:test | jq '.[0].Config.Entrypoint'
```

### 12.3 Kubernetes
```bash
# Dry run
kubectl apply --dry-run=client -k k8s/

# Check for errors
kubectl apply --dry-run=server -k k8s/
```

### 12.4 No Remaining References
```bash
# Should return only this file and CHANGELOG
rg -i "\\bigu\\b" --type-not md

# Check specific patterns
rg "from igu\.|import igu\." --type py  # Should return nothing
rg "igu-system" --type yaml  # Should return nothing
```

---

## 13. Migration Guide for Existing Users

### 13.1 Local Development
```bash
# 1. Pull latest code
git pull origin main

# 2. Reinstall package
pip uninstall igu
pip install -e .

# 3. Rename config directory (optional, backward compatible)
mv ~/.guard ~/.guard

# 4. Update command usage
guard --help  # instead of: igu --help
```

### 13.2 Kubernetes Deployments
```bash
# 1. Delete old namespace (or rename)
kubectl delete namespace igu-system

# 2. Deploy new version
kubectl apply -k k8s/

# 3. Verify deployment
kubectl get all -n guard-system
```

### 13.3 AWS Resources (Optional)
```bash
# Secrets can coexist, but for consistency:
# 1. Copy secrets to new paths
aws secretsmanager create-secret \
    --name guard/gitlab-token \
    --secret-string "$(aws secretsmanager get-secret-value --secret-id igu/gitlab-token --query SecretString --output text)"

# 2. DynamoDB tables can coexist
# Or rename table via AWS Console/CLI
```

---

## 14. Communication Plan

### 14.1 Internal Announcement
- Slack/Teams notification about rename
- Link to this migration guide
- Timeline for deprecation of old names

### 14.2 Repository Updates
- Update repository description
- Add topic tags in GitLab
- Update any linked projects/wikis

### 14.3 Deprecation Notice
Add to README.md temporarily:
```markdown
> **⚠️ Project Renamed:** This project was previously known as GUARD (GitOps Upgrade Automation with Rollback Detection).
> All functionality remains the same. See [CHANGELOG.md](CHANGELOG.md) for migration details.
```

---

## 15. Rollback Plan

If issues arise:
1. Revert git commit: `git revert <rename-commit>`
2. Restore from tag: `git checkout v0.1.0-igu`
3. Redeploy old version from backup Docker images
4. AWS resources (secrets, DynamoDB) remain unchanged

---

## Estimated Effort

- **Preparation:** 30 minutes
- **Code changes:** 2-3 hours
- **Documentation updates:** 1-2 hours
- **Testing:** 1 hour
- **Deployment:** 1 hour
- **Total:** ~5-8 hours

---

## Notes

- Consider doing this in a feature branch first: `git checkout -b feature/rename-to-guard`
- Test thoroughly before merging to main
- Coordinate with team for deployment timing
- Keep old DynamoDB tables and secrets for backward compatibility during transition
- Consider maintaining a redirect or alias for `igu` command temporarily

---

**Status:** Ready for implementation
**Created:** 2025-01-XX
**Last Updated:** 2025-01-XX

"""Unit tests for FluxConfigManager.

Tests YAML parsing, version updating, and validation for Flux HelmRelease configurations.
"""

import pytest
import yaml

from guard.gitops.flux_config import FluxConfigManager


class TestFluxConfigManagerParsing:
    """Tests for YAML parsing functionality."""

    def test_parse_valid_helmrelease(self):
        """Test parsing a valid HelmRelease YAML."""
        content = """
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: istio-base
  namespace: istio-system
spec:
  chart:
    spec:
      chart: base
      version: "1.19.0"
      sourceRef:
        kind: HelmRepository
        name: istio
"""
        result = FluxConfigManager.parse_helmrelease(content)

        assert result is not None
        assert result["kind"] == "HelmRelease"
        assert result["metadata"]["name"] == "istio-base"
        assert result["spec"]["chart"]["spec"]["version"] == "1.19.0"

    def test_parse_empty_content(self):
        """Test parsing empty content returns None."""
        result = FluxConfigManager.parse_helmrelease("")

        assert result is None

    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML raises exception."""
        invalid_yaml = """
        invalid: yaml: content:
            - with bad indentation
        """

        with pytest.raises(yaml.YAMLError):
            FluxConfigManager.parse_helmrelease(invalid_yaml)

    def test_parse_multiline_helmrelease(self):
        """Test parsing HelmRelease with multiple sections."""
        content = """
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: istio-base
  namespace: istio-system
spec:
  interval: 5m
  chart:
    spec:
      chart: base
      version: "1.19.0"
      sourceRef:
        kind: HelmRepository
        name: istio
        namespace: istio-system
  values:
    global:
      istioNamespace: istio-system
"""
        result = FluxConfigManager.parse_helmrelease(content)

        assert result["spec"]["interval"] == "5m"
        assert result["spec"]["values"]["global"]["istioNamespace"] == "istio-system"


class TestFluxConfigManagerVersionUpdate:
    """Tests for version update functionality."""

    @pytest.fixture
    def sample_config(self):
        """Provide a sample HelmRelease config."""
        return {
            "apiVersion": "helm.toolkit.fluxcd.io/v2beta1",
            "kind": "HelmRelease",
            "metadata": {"name": "istio-base", "namespace": "istio-system"},
            "spec": {
                "chart": {
                    "spec": {
                        "chart": "base",
                        "version": "1.19.0",
                        "sourceRef": {"kind": "HelmRepository", "name": "istio"},
                    }
                }
            },
        }

    def test_update_version_success(self, sample_config):
        """Test successfully updating version."""
        updated = FluxConfigManager.update_version(sample_config, "1.20.0")

        assert updated["spec"]["chart"]["spec"]["version"] == "1.20.0"
        # Ensure original structure preserved
        assert updated["kind"] == "HelmRelease"
        assert updated["metadata"]["name"] == "istio-base"

    def test_update_version_with_v_prefix(self, sample_config):
        """Test updating version with 'v' prefix strips the prefix."""
        updated = FluxConfigManager.update_version(sample_config, "v1.20.0")

        assert updated["spec"]["chart"]["spec"]["version"] == "1.20.0"

    def test_update_version_empty_config(self):
        """Test updating empty config raises ValueError."""
        with pytest.raises(ValueError, match="Empty configuration"):
            FluxConfigManager.update_version({}, "1.20.0")

    def test_update_version_missing_spec(self):
        """Test updating config without spec raises ValueError."""
        config = {"kind": "HelmRelease", "metadata": {"name": "test"}}

        with pytest.raises(ValueError, match="Missing 'spec' in HelmRelease"):
            FluxConfigManager.update_version(config, "1.20.0")

    def test_update_version_missing_chart(self):
        """Test updating config without chart raises ValueError."""
        config = {"spec": {"interval": "5m"}}

        with pytest.raises(ValueError, match="Missing 'spec.chart' in HelmRelease"):
            FluxConfigManager.update_version(config, "1.20.0")

    def test_update_version_missing_chart_spec(self):
        """Test updating config without chart.spec raises ValueError."""
        config = {"spec": {"chart": {"sourceRef": {"name": "istio"}}}}

        with pytest.raises(ValueError, match="Missing 'spec.chart.spec' in HelmRelease"):
            FluxConfigManager.update_version(config, "1.20.0")

    def test_update_version_preserves_other_fields(self, sample_config):
        """Test that updating version preserves all other fields."""
        sample_config["spec"]["interval"] = "10m"
        sample_config["spec"]["values"] = {"global": {"istioNamespace": "istio-system"}}

        updated = FluxConfigManager.update_version(sample_config, "1.20.0")

        assert updated["spec"]["interval"] == "10m"
        assert updated["spec"]["values"]["global"]["istioNamespace"] == "istio-system"
        assert updated["spec"]["chart"]["spec"]["version"] == "1.20.0"

    def test_update_version_multiple_times(self, sample_config):
        """Test updating version multiple times."""
        updated1 = FluxConfigManager.update_version(sample_config, "1.20.0")
        assert updated1["spec"]["chart"]["spec"]["version"] == "1.20.0"

        updated2 = FluxConfigManager.update_version(updated1, "1.21.0")
        assert updated2["spec"]["chart"]["spec"]["version"] == "1.21.0"

        updated3 = FluxConfigManager.update_version(updated2, "v1.22.0")
        assert updated3["spec"]["chart"]["spec"]["version"] == "1.22.0"

    def test_update_version_with_missing_version_field(self):
        """Test updating config where version field doesn't exist yet."""
        config = {"spec": {"chart": {"spec": {"chart": "base"}}}}

        updated = FluxConfigManager.update_version(config, "1.20.0")
        assert updated["spec"]["chart"]["spec"]["version"] == "1.20.0"

    def test_update_version_none_config(self):
        """Test updating None config raises ValueError."""
        with pytest.raises(ValueError, match="Empty configuration"):
            FluxConfigManager.update_version(None, "1.20.0")


class TestFluxConfigManagerYamlConversion:
    """Tests for YAML conversion functionality."""

    def test_to_yaml_simple_config(self):
        """Test converting simple config to YAML."""
        config = {
            "apiVersion": "v1",
            "kind": "HelmRelease",
            "metadata": {"name": "test"},
        }

        yaml_str = FluxConfigManager.to_yaml(config)

        assert "apiVersion: v1" in yaml_str
        assert "kind: HelmRelease" in yaml_str
        assert "name: test" in yaml_str

    def test_to_yaml_complex_config(self):
        """Test converting complex config to YAML."""
        config = {
            "apiVersion": "helm.toolkit.fluxcd.io/v2beta1",
            "kind": "HelmRelease",
            "metadata": {"name": "istio-base", "namespace": "istio-system"},
            "spec": {
                "chart": {
                    "spec": {
                        "version": "1.20.0",
                        "sourceRef": {"kind": "HelmRepository"},
                    }
                }
            },
        }

        yaml_str = FluxConfigManager.to_yaml(config)

        # Parse it back to verify it's valid YAML
        parsed = yaml.safe_load(yaml_str)
        assert parsed == config

    def test_to_yaml_empty_config(self):
        """Test converting empty config to YAML."""
        yaml_str = FluxConfigManager.to_yaml({})

        assert yaml_str == "{}\n"

    def test_to_yaml_preserves_structure(self):
        """Test that to_yaml preserves nested structure."""
        config = {
            "level1": {
                "level2": {"level3": {"version": "1.20.0"}},
                "other": "value",
            }
        }

        yaml_str = FluxConfigManager.to_yaml(config)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["level1"]["level2"]["level3"]["version"] == "1.20.0"
        assert parsed["level1"]["other"] == "value"

    def test_to_yaml_with_lists(self):
        """Test converting config with lists to YAML."""
        config = {
            "spec": {
                "values": {
                    "tolerations": [
                        {"key": "node-role", "operator": "Equal", "value": "istio"},
                        {"key": "env", "operator": "Equal", "value": "prod"},
                    ]
                }
            }
        }

        yaml_str = FluxConfigManager.to_yaml(config)
        parsed = yaml.safe_load(yaml_str)

        assert len(parsed["spec"]["values"]["tolerations"]) == 2
        assert parsed["spec"]["values"]["tolerations"][0]["key"] == "node-role"


class TestFluxConfigManagerIntegration:
    """Integration tests for FluxConfigManager workflows."""

    def test_parse_update_and_convert_workflow(self):
        """Test full workflow: parse -> update -> convert."""
        original_yaml = """
apiVersion: helm.toolkit.fluxcd.io/v2beta1
kind: HelmRelease
metadata:
  name: istio-base
  namespace: istio-system
spec:
  chart:
    spec:
      chart: base
      version: "1.19.0"
      sourceRef:
        kind: HelmRepository
        name: istio
"""

        # Parse
        config = FluxConfigManager.parse_helmrelease(original_yaml)
        assert config["spec"]["chart"]["spec"]["version"] == "1.19.0"

        # Update version
        updated_config = FluxConfigManager.update_version(config, "v1.20.0")
        assert updated_config["spec"]["chart"]["spec"]["version"] == "1.20.0"

        # Convert back to YAML
        updated_yaml = FluxConfigManager.to_yaml(updated_config)

        # Parse again to verify
        final_config = FluxConfigManager.parse_helmrelease(updated_yaml)
        assert final_config["spec"]["chart"]["spec"]["version"] == "1.20.0"
        assert final_config["metadata"]["name"] == "istio-base"

    def test_multiple_version_updates(self):
        """Test multiple sequential version updates."""
        yaml_content = """
spec:
  chart:
    spec:
      version: "1.19.0"
"""

        config = FluxConfigManager.parse_helmrelease(yaml_content)

        # Update multiple times
        for version in ["1.20.0", "1.21.0", "1.22.0"]:
            config = FluxConfigManager.update_version(config, version)
            assert config["spec"]["chart"]["spec"]["version"] == version

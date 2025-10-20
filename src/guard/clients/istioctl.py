"""Istioctl wrapper for Istio operations."""

import json
import subprocess
from typing import Any

from guard.core.exceptions import IstioError
from guard.utils.logging import get_logger

logger = get_logger(__name__)


class IstioctlWrapper:
    """Wrapper for istioctl command-line tool."""

    def __init__(self, kubeconfig_path: str | None = None, context: str | None = None):
        """Initialize istioctl wrapper.

        Args:
            kubeconfig_path: Path to kubeconfig file (optional)
            context: Kubernetes context to use (optional)
        """
        self.kubeconfig_path = kubeconfig_path
        self.context = context

        logger.debug("istioctl_wrapper_initialized", context=context)

    def _run_command(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run istioctl command.

        Args:
            args: Command arguments
            check: Raise exception on non-zero exit code

        Returns:
            CompletedProcess instance

        Raises:
            IstioError: If command fails
        """
        cmd = ["istioctl"] + args

        # Add kubeconfig if specified
        if self.kubeconfig_path:
            cmd.extend(["--kubeconfig", self.kubeconfig_path])

        # Add context if specified
        if self.context:
            cmd.extend(["--context", self.context])

        logger.debug("running_istioctl_command", command=" ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=check,
            )

            logger.debug(
                "istioctl_command_completed",
                returncode=result.returncode,
            )

            return result

        except subprocess.CalledProcessError as e:
            logger.error(
                "istioctl_command_failed",
                command=" ".join(cmd),
                returncode=e.returncode,
                stderr=e.stderr,
            )
            raise IstioError(f"istioctl command failed: {e.stderr or e.stdout}") from e
        except FileNotFoundError as e:
            logger.error("istioctl_not_found")
            raise IstioError("istioctl command not found. Please install Istio CLI.") from e

    def analyze(self, namespace: str | None = None) -> tuple[bool, str]:
        """Run istioctl analyze to check configuration.

        Args:
            namespace: Namespace to analyze (optional, analyzes all if not specified)

        Returns:
            Tuple of (no_issues: bool, output: str)

        Raises:
            IstioError: If analysis fails
        """
        try:
            logger.debug("running_istioctl_analyze", namespace=namespace)

            args = ["analyze"]
            if namespace:
                args.extend(["-n", namespace])

            result = self._run_command(args, check=False)

            # istioctl analyze returns 0 if no issues
            no_issues = result.returncode == 0
            output = result.stdout + result.stderr

            logger.info(
                "istioctl_analyze_completed",
                no_issues=no_issues,
                namespace=namespace,
            )

            return no_issues, output

        except Exception as e:
            logger.error("istioctl_analyze_failed", error=str(e))
            raise IstioError(f"Failed to run istioctl analyze: {e}") from e

    def proxy_status(self) -> dict[str, Any]:
        """Get proxy sync status.

        Returns:
            Proxy status as dictionary

        Raises:
            IstioError: If command fails
        """
        try:
            logger.debug("getting_proxy_status")

            result = self._run_command(["proxy-status", "-o", "json"])
            status = json.loads(result.stdout)

            logger.info("proxy_status_retrieved")
            return status

        except json.JSONDecodeError as e:
            logger.error("proxy_status_json_parse_failed", error=str(e))
            raise IstioError("Failed to parse proxy status JSON") from e
        except Exception as e:
            logger.error("proxy_status_failed", error=str(e))
            raise IstioError(f"Failed to get proxy status: {e}") from e

    def version(self) -> dict[str, Any]:
        """Get Istio version information.

        Returns:
            Version info as dictionary

        Raises:
            IstioError: If command fails
        """
        try:
            logger.debug("getting_istio_version")

            result = self._run_command(["version", "-o", "json"])
            version_info = json.loads(result.stdout)

            logger.info("istio_version_retrieved")
            return version_info

        except json.JSONDecodeError as e:
            logger.error("version_json_parse_failed", error=str(e))
            raise IstioError("Failed to parse version JSON") from e
        except Exception as e:
            logger.error("istio_version_failed", error=str(e))
            raise IstioError(f"Failed to get Istio version: {e}") from e

    def check_proxy_sync(self) -> tuple[bool, list[str]]:
        """Check if all proxies are synced.

        Returns:
            Tuple of (all_synced: bool, unsynced_proxies: list)

        Raises:
            IstioError: If check fails
        """
        try:
            logger.debug("checking_proxy_sync")

            status = self.proxy_status()

            # Parse proxy status to find unsynced proxies
            unsynced = []

            # Status format varies, try to handle both list and dict formats
            if isinstance(status, list):
                for proxy in status:
                    if proxy.get("sync_status") != "SYNCED":
                        unsynced.append(proxy.get("name", "unknown"))
            elif isinstance(status, dict):
                for name, info in status.items():
                    if isinstance(info, dict) and info.get("sync_status") != "SYNCED":
                        unsynced.append(name)

            all_synced = len(unsynced) == 0

            logger.info(
                "proxy_sync_check_completed",
                all_synced=all_synced,
                unsynced_count=len(unsynced),
            )

            return all_synced, unsynced

        except Exception as e:
            logger.error("proxy_sync_check_failed", error=str(e))
            raise IstioError(f"Failed to check proxy sync: {e}") from e

    def verify_install(self) -> tuple[bool, str]:
        """Verify Istio installation.

        Returns:
            Tuple of (verified: bool, output: str)

        Raises:
            IstioError: If verification fails
        """
        try:
            logger.debug("verifying_istio_install")

            result = self._run_command(["verify-install"], check=False)

            verified = result.returncode == 0
            output = result.stdout + result.stderr

            logger.info("istio_verify_install_completed", verified=verified)

            return verified, output

        except Exception as e:
            logger.error("istio_verify_install_failed", error=str(e))
            raise IstioError(f"Failed to verify Istio install: {e}") from e

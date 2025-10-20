"""Main CLI entry point for IGU."""

import click
from rich.console import Console

from igu import __version__

console = Console()


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--config",
    type=click.Path(exists=True),
    default="~/.igu/config.yaml",
    help="Path to configuration file",
)
@click.pass_context
def cli(ctx: click.Context, config: str) -> None:
    """Istio GitOps Upgrader (IGU) - Automate safe Istio upgrades."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
@click.option("--batch", required=True, help="Batch name to upgrade")
@click.option("--target-version", required=True, help="Target Istio version")
@click.option("--dry-run", is_flag=True, help="Perform dry run without creating MR")
@click.option("--max-concurrent", type=int, default=5, help="Max concurrent cluster operations")
@click.pass_context
def run(ctx: click.Context, batch: str, target_version: str, dry_run: bool, max_concurrent: int) -> None:
    """Run pre-checks and create upgrade MR for a batch."""
    import asyncio
    from pathlib import Path

    from guard.core.config import IguConfig
    from guard.registry.cluster_registry import ClusterRegistry
    from guard.adapters.dynamodb_adapter import DynamoDBAdapter
    from guard.adapters.aws_adapter import AWSAdapter
    from guard.adapters.k8s_adapter import KubernetesAdapter
    from guard.adapters.datadog_adapter import DatadogAdapter
    from guard.adapters.gitlab_adapter import GitLabAdapter
    from guard.gitops.gitops_orchestrator import GitOpsOrchestrator
    from guard.gitops.updaters.istio_helm_updater import IstioHelmUpdater
    from guard.checks.pre_check_engine import PreCheckOrchestrator
    from guard.services.istio.istio_service import IstioService
    from guard.interfaces.check import CheckContext
    from guard.utils.logging import get_logger

    logger = get_logger(__name__)

    console.print(f"[bold blue]IGU Run Command[/bold blue]")
    console.print(f"Batch: {batch}")
    console.print(f"Target Version: {target_version}")
    console.print(f"Dry Run: {dry_run}")
    console.print(f"Max Concurrent: {max_concurrent}\n")

    async def _process_cluster(
        cluster,
        semaphore,
        app_config,
        target_version,
        dry_run,
        aws_adapter,
        datadog_adapter,
        gitlab_adapter,
        helm_updater,
    ):
        """Process a single cluster with error isolation."""
        async with semaphore:
            try:
                console.print(f"[bold]Processing cluster: {cluster.cluster_id}[/bold]")

                # Run pre-checks
                console.print("  Running pre-checks...")
                k8s_adapter = KubernetesAdapter(context=cluster.cluster_id)

                # Initialize check orchestrator and register checks
                check_orchestrator = PreCheckOrchestrator()

                # Register Istio checks
                istio_service = IstioService()
                istio_service.register_checks(check_orchestrator)

                # Build check context with all required providers
                check_context = CheckContext(
                    kubernetes_provider=k8s_adapter,
                    cloud_provider=aws_adapter,
                    metrics_provider=datadog_adapter,
                    extra_context={
                        "kubeconfig_path": None,  # Use default kubeconfig
                        "istioctl": None,  # Will be created by check if needed
                    },
                )

                check_results = await check_orchestrator.run_all_checks(cluster, check_context)
                all_passed = all(r.passed for r in check_results)

                if not all_passed:
                    console.print(f"  [red]✗ Pre-checks failed[/red]")
                    for result in check_results:
                        if not result.passed:
                            console.print(f"    - {result.check_name}: {result.message}")
                    logger.error(
                        "cluster_pre_check_failed",
                        cluster_id=cluster.cluster_id,
                        batch_id=batch,
                    )
                    return {"cluster_id": cluster.cluster_id, "status": "pre_check_failed"}

                console.print("  [green]✓ All pre-checks passed[/green]")

                # Create upgrade MR
                if not dry_run:
                    console.print("  Creating GitLab MR...")
                    orchestrator = GitOpsOrchestrator(
                        gitops_provider=gitlab_adapter,
                        config_updater=helm_updater,
                    )

                    mr_url = await orchestrator.create_upgrade_mr(
                        cluster=cluster,
                        target_version=target_version,
                    )

                    console.print(f"  [green]✓ MR created: {mr_url}[/green]\n")
                    logger.info(
                        "cluster_mr_created",
                        cluster_id=cluster.cluster_id,
                        mr_url=mr_url,
                    )
                    return {"cluster_id": cluster.cluster_id, "status": "success", "mr_url": mr_url}
                else:
                    console.print("  [yellow]Dry-run: Skipping MR creation[/yellow]\n")
                    return {"cluster_id": cluster.cluster_id, "status": "dry_run_success"}

            except Exception as e:
                console.print(f"  [red]✗ Error processing cluster: {e}[/red]\n")
                logger.error(
                    "cluster_processing_failed",
                    cluster_id=cluster.cluster_id,
                    batch_id=batch,
                    error=str(e),
                )
                return {"cluster_id": cluster.cluster_id, "status": "error", "error": str(e)}

    async def _run_upgrade():
        try:
            # Load configuration
            config_path = Path(ctx.obj['config']).expanduser()
            console.print(f"Loading config from {config_path}...")
            app_config = IguConfig.from_file(str(config_path))

            # Initialize cluster registry
            console.print("Initializing cluster registry...")
            dynamodb = DynamoDBAdapter(region=app_config.aws.region)
            registry = ClusterRegistry(dynamodb)

            # Get clusters for batch
            console.print(f"Fetching clusters for batch: {batch}...")
            clusters = await registry.get_clusters_by_batch(batch)

            if not clusters:
                console.print(f"[red]No clusters found for batch: {batch}[/red]")
                return

            console.print(f"Found {len(clusters)} cluster(s) in batch {batch}\n")

            # Initialize adapters and clients
            aws_adapter = AWSAdapter(region=app_config.aws.region)
            datadog_adapter = DatadogAdapter(
                api_key=app_config.datadog.api_key,
                app_key=app_config.datadog.app_key,
            )
            gitlab_adapter = GitLabAdapter(
                url=app_config.gitlab.url,
                token=app_config.gitlab.token,
            )

            # Initialize config updater
            helm_updater = IstioHelmUpdater()

            # Process clusters with bounded concurrency
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [
                _process_cluster(
                    cluster,
                    semaphore,
                    app_config,
                    target_version,
                    dry_run,
                    aws_adapter,
                    datadog_adapter,
                    gitlab_adapter,
                    helm_updater,
                )
                for cluster in clusters
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Summarize results
            console.print("\n[bold]Batch Processing Summary[/bold]")
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") in ["success", "dry_run_success"])
            failed_count = len(results) - success_count

            console.print(f"  Total: {len(results)}")
            console.print(f"  [green]Success: {success_count}[/green]")
            console.print(f"  [red]Failed: {failed_count}[/red]\n")

            logger.info(
                "batch_processing_complete",
                batch_id=batch,
                total=len(results),
                success=success_count,
                failed=failed_count,
            )

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
            logger.error("batch_processing_error", batch_id=batch, error=str(e))
            raise

    asyncio.run(_run_upgrade())


@cli.command()
@click.option("--batch", required=True, help="Batch name to monitor")
@click.option("--soak-period", type=int, default=60, help="Soak period in minutes")
@click.pass_context
def monitor(ctx: click.Context, batch: str, soak_period: int) -> None:
    """Monitor post-upgrade validation for a batch."""
    console.print(f"[bold green]IGU Monitor Command[/bold green]")
    console.print(f"Batch: {batch}")
    console.print(f"Soak Period: {soak_period} minutes")
    console.print(f"Config: {ctx.obj['config']}")
    console.print("\n[yellow]⚠️  Implementation pending[/yellow]")


@cli.command()
@click.option("--batch", required=True, help="Batch name to rollback")
@click.pass_context
def rollback(ctx: click.Context, batch: str) -> None:
    """Trigger manual rollback for a batch."""
    console.print(f"[bold red]IGU Rollback Command[/bold red]")
    console.print(f"Batch: {batch}")
    console.print(f"Config: {ctx.obj['config']}")
    console.print("\n[yellow]⚠️  Implementation pending[/yellow]")


@cli.command(name="list")
@click.option("--batch", help="Filter by batch name")
@click.option("--environment", help="Filter by environment")
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def list_clusters(
    ctx: click.Context, batch: str | None, environment: str | None, format: str
) -> None:
    """List clusters and their status."""
    console.print(f"[bold cyan]IGU List Command[/bold cyan]")
    console.print(f"Batch Filter: {batch or 'None'}")
    console.print(f"Environment Filter: {environment or 'None'}")
    console.print(f"Format: {format}")
    console.print(f"Config: {ctx.obj['config']}")
    console.print("\n[yellow]⚠️  Implementation pending[/yellow]")


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate configuration and connectivity."""
    console.print(f"[bold magenta]IGU Validate Command[/bold magenta]")
    console.print(f"Config: {ctx.obj['config']}")
    console.print("\n[yellow]⚠️  Implementation pending[/yellow]")


if __name__ == "__main__":
    cli()

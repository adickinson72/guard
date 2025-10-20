#!/bin/bash
set -e

echo "Bootstrapping IGU..."

# Create config directory
mkdir -p ~/.igu

# Check for example config
if [ ! -f ~/.igu/config.yaml ]; then
    echo "Copying example config to ~/.igu/config.yaml"
    cp examples/config.yaml.example ~/.igu/config.yaml
    echo "Please edit ~/.igu/config.yaml with your settings"
fi

# Check for istioctl
if ! command -v istioctl &> /dev/null; then
    echo "WARNING: istioctl not found. Please install Istio CLI:"
    echo "  curl -L https://istio.io/downloadIstio | sh -"
fi

# Check for kubectl
if ! command -v kubectl &> /dev/null; then
    echo "WARNING: kubectl not found. Please install kubectl"
fi

echo ""
echo "Bootstrap complete!"
echo "Next steps:"
echo "  1. Edit ~/.igu/config.yaml"
echo "  2. Run: ./scripts/setup-dynamodb.sh"
echo "  3. Setup AWS Secrets Manager secrets"
echo "  4. Run: igu validate"

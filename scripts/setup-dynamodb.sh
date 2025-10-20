#!/bin/bash
set -e

# Setup DynamoDB tables for GUARD

TABLE_NAME="${1:-guard-cluster-registry}"
REGION="${2:-us-east-1}"

echo "Creating DynamoDB table: $TABLE_NAME in region: $REGION"

aws dynamodb create-table \
    --table-name "$TABLE_NAME" \
    --attribute-definitions \
        AttributeName=cluster_id,AttributeType=S \
        AttributeName=batch_id,AttributeType=S \
    --key-schema AttributeName=cluster_id,KeyType=HASH \
    --global-secondary-indexes \
        "[{
            \"IndexName\": \"batch-index\",
            \"KeySchema\": [{\"AttributeName\":\"batch_id\",\"KeyType\":\"HASH\"}],
            \"Projection\": {\"ProjectionType\":\"ALL\"},
            \"ProvisionedThroughput\": {\"ReadCapacityUnits\": 5, \"WriteCapacityUnits\": 5}
        }]" \
    --billing-mode PAY_PER_REQUEST \
    --region "$REGION"

echo "DynamoDB table created successfully!"
echo ""
echo "To create the locks table, run:"
echo "  aws dynamodb create-table --table-name guard-locks \\"
echo "    --attribute-definitions AttributeName=resource_id,AttributeType=S \\"
echo "    --key-schema AttributeName=resource_id,KeyType=HASH \\"
echo "    --billing-mode PAY_PER_REQUEST --region $REGION"

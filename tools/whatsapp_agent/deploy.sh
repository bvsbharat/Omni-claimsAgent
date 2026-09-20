#!/usr/bin/env bash
#
# Deploy the ClaimPilot WhatsApp agent loop:
#   - DynamoDB table  claimpilot-conversations
#   - IAM role        claimpilot-wa-agent-role  (Bedrock + WhatsApp + DDB + SQS + logs)
#   - Lambda          claimpilot-wa-agent
#   - Event source    the existing WhatsApp events queue -> Lambda
#
# Idempotent-ish: re-running updates the function code and skips existing resources.
# Uses the repo AWS wrapper (working CLI + clean creds).
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS="$DIR/../../scripts/awscds.sh"
REGION="us-east-1"
ACCOUNT="203918842720"

FUNC="claimpilot-wa-agent"
ROLE="claimpilot-wa-agent-role"
TABLE="claimpilot-conversations"
QUEUE_ARN="arn:aws:sqs:us-east-1:${ACCOUNT}:cds-whatsapp-events-debug"
QUEUE_URL="https://sqs.us-east-1.amazonaws.com/${ACCOUNT}/cds-whatsapp-events-debug"
ORIGINATION_PHONE_ID="phone-number-id-c6422678213d4226becc4aa290a85dca"
MODEL_ID="us.anthropic.claude-sonnet-4-6"

echo "== 1. DynamoDB table =="
"$AWS" dynamodb describe-table --region "$REGION" --table-name "$TABLE" >/dev/null 2>&1 \
  && echo "   table exists" \
  || "$AWS" dynamodb create-table --region "$REGION" --table-name "$TABLE" \
       --attribute-definitions AttributeName=phone,AttributeType=S \
       --key-schema AttributeName=phone,KeyType=HASH \
       --billing-mode PAY_PER_REQUEST >/dev/null && echo "   table created"

echo "== 2. IAM role =="
if ! "$AWS" iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  "$AWS" iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  echo "   role created"
else
  echo "   role exists"
fi
"$AWS" iam put-role-policy --role-name "$ROLE" --policy-name claimpilot-inline \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\",\"bedrock:Converse\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"social-messaging:SendWhatsAppMessage\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"},
      {\"Effect\":\"Allow\",\"Action\":[\"sqs:ReceiveMessage\",\"sqs:DeleteMessage\",\"sqs:GetQueueAttributes\"],\"Resource\":\"${QUEUE_ARN}\"}
    ]}" >/dev/null
echo "   inline policy set"
echo "   waiting for role propagation..."; sleep 10

echo "== 3. package =="
BUILD="$(mktemp -d)"
cp "$DIR/lambda_function.py" "$DIR/claim_agent.py" "$BUILD/"
( cd "$BUILD" && zip -q function.zip lambda_function.py claim_agent.py )

echo "== 4. Lambda =="
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"
ENV="Variables={CONV_TABLE=${TABLE},ORIGINATION_PHONE_ID=${ORIGINATION_PHONE_ID},META_API_VERSION=v20.0,CLAIM_MODEL_ID=${MODEL_ID}}"
if "$AWS" lambda get-function --region "$REGION" --function-name "$FUNC" >/dev/null 2>&1; then
  "$AWS" lambda update-function-code --region "$REGION" --function-name "$FUNC" \
    --zip-file "fileb://$BUILD/function.zip" >/dev/null
  "$AWS" lambda update-function-configuration --region "$REGION" --function-name "$FUNC" \
    --environment "$ENV" --timeout 60 --memory-size 256 >/dev/null
  echo "   function updated"
else
  "$AWS" lambda create-function --region "$REGION" --function-name "$FUNC" \
    --runtime python3.12 --handler lambda_function.lambda_handler \
    --role "$ROLE_ARN" --timeout 60 --memory-size 256 \
    --environment "$ENV" \
    --zip-file "fileb://$BUILD/function.zip" >/dev/null
  echo "   function created"
fi

echo "== 5. SQS event source mapping =="
EXISTING=$("$AWS" lambda list-event-source-mappings --region "$REGION" --function-name "$FUNC" \
  --query "EventSourceMappings[?EventSourceArn=='${QUEUE_ARN}'].UUID" --output text 2>/dev/null)
if [[ -z "$EXISTING" || "$EXISTING" == "None" ]]; then
  "$AWS" lambda create-event-source-mapping --region "$REGION" --function-name "$FUNC" \
    --event-source-arn "$QUEUE_ARN" --batch-size 5 >/dev/null && echo "   mapping created"
else
  echo "   mapping exists ($EXISTING)"
fi

rm -rf "$BUILD"
echo "== done =="
echo "Tail logs with:"
echo "  $AWS logs tail /aws/lambda/${FUNC} --follow --region ${REGION}"

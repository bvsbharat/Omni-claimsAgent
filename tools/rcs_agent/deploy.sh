#!/usr/bin/env bash
#
# Deploy the ClaimPilot RCS agent loop.
#   - DynamoDB table  claimpilot-claims
#   - IAM role        claimpilot-rcs-agent-role  (Bedrock + sms-voice + DDB + S3 + SQS + logs)
#   - Lambda          claimpilot-rcs-agent  (python3.12, arm64) w/ bundled Pillow
#   - Event source    cds-eum-events-debug queue -> Lambda
#
# Idempotent: re-run to update code/config; existing resources are reused.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS="$DIR/../../scripts/awscds.sh"
REGION="us-east-1"
ACCOUNT="203918842720"

FUNC="claimpilot-rcs-agent"
ROLE="claimpilot-rcs-agent-role"
TABLE="claimpilot-claims"
QUEUE_ARN="arn:aws:sqs:us-east-1:${ACCOUNT}:cds-eum-events-debug"
WA_QUEUE_ARN="arn:aws:sqs:us-east-1:${ACCOUNT}:cds-whatsapp-events-debug"
WA_QUEUE_URL="https://sqs.us-east-1.amazonaws.com/${ACCOUNT}/cds-whatsapp-events-debug"
MEDIA_BUCKET="claimpilot-rcs-media-${ACCOUNT}"
RCS_AGENT_ARN="arn:aws:sms-voice:us-east-1:${ACCOUNT}:rcs-agent/rcs-f9a76b2b8448418fb9ae6747622beaa6"
WA_PHONE_ID="phone-number-id-c6422678213d4226becc4aa290a85dca"
MODEL_ID="us.anthropic.claude-sonnet-4-6"
ARCH="arm64"           # Graviton; matches the Pillow wheel we fetch
PY="python3.12"

echo "== 1. DynamoDB table =="
"$AWS" dynamodb describe-table --region "$REGION" --table-name "$TABLE" >/dev/null 2>&1 \
  && echo "   exists" \
  || { "$AWS" dynamodb create-table --region "$REGION" --table-name "$TABLE" \
        --attribute-definitions AttributeName=phone,AttributeType=S \
        --key-schema AttributeName=phone,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST >/dev/null && echo "   created"; }

echo "== 2. IAM role =="
if ! "$AWS" iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  "$AWS" iam create-role --role-name "$ROLE" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  echo "   created"
else
  echo "   exists"
fi
"$AWS" iam put-role-policy --role-name "$ROLE" --policy-name claimpilot-rcs-inline \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\",\"bedrock:Converse\"],\"Resource\":[\"arn:aws:bedrock:*::foundation-model/*\",\"arn:aws:bedrock:*:${ACCOUNT}:inference-profile/*\"]},
      {\"Effect\":\"Allow\",\"Action\":[\"bedrock:ApplyGuardrail\"],\"Resource\":\"arn:aws:bedrock:${REGION}:${ACCOUNT}:guardrail/*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"sms-voice:SendTextMessage\",\"sms-voice:SendRcsMessage\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"social-messaging:SendWhatsAppMessage\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"transcribe:StartTranscriptionJob\",\"transcribe:GetTranscriptionJob\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"textract:AnalyzeDocument\",\"textract:StartDocumentAnalysis\",\"textract:GetDocumentAnalysis\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"ses:SendEmail\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"dynamodb:GetItem\",\"dynamodb:PutItem\"],\"Resource\":\"arn:aws:dynamodb:${REGION}:${ACCOUNT}:table/${TABLE}\"},
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\"],\"Resource\":\"arn:aws:s3:::${MEDIA_BUCKET}/*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"sqs:ReceiveMessage\",\"sqs:DeleteMessage\",\"sqs:GetQueueAttributes\"],\"Resource\":[\"${QUEUE_ARN}\",\"${WA_QUEUE_ARN}\"]}
    ]}" >/dev/null
echo "   inline policy set"
echo "   waiting for role propagation..."; sleep 10

echo "== 3. package (with Pillow for ${ARCH}) =="
BUILD="$(mktemp -d)"
cp "$DIR/lambda_function.py" "$DIR/claim_agent.py" "$DIR/confirmation_image.py" \
   "$DIR/media.py" "$DIR/channels.py" "$DIR/email_tool.py" "$DIR/settlement.py" \
   "$DIR/ocr.py" "$BUILD/"
echo "   fetching Pillow wheel (manylinux ${ARCH}, cp312)..."
$PY -m pip install \
  --platform manylinux2014_aarch64 \
  --implementation cp --python-version 3.12 --only-binary=:all: \
  --target "$BUILD" "pillow>=10,<11" >/tmp/pillow_pip.log 2>&1 \
  || { echo "   pip failed, see /tmp/pillow_pip.log"; tail -5 /tmp/pillow_pip.log; }
echo "   bundling current boto3/botocore (Lambda runtime's is too old for send_rcs_message)..."
$PY -m pip install --target "$BUILD" "boto3>=1.42" >/tmp/boto3_pip.log 2>&1 \
  || { echo "   boto3 pip failed, see /tmp/boto3_pip.log"; tail -5 /tmp/boto3_pip.log; }
( cd "$BUILD" && zip -qr function.zip . -x "*.dist-info/*" "*.pyc" )
echo "   zip: $(du -h "$BUILD/function.zip" | cut -f1)"

echo "== 4. Lambda =="
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"
SES_SENDER="ClaimPilot Claims <uibharat@gmail.com>"
GUARDRAIL_ID="aba98ba9d4o9"
GUARDRAIL_VERSION="1"
ENV="Variables={CONV_TABLE=${TABLE},RCS_AGENT_ARN=${RCS_AGENT_ARN},WA_ORIGINATION_PHONE_ID=${WA_PHONE_ID},META_API_VERSION=v20.0,MEDIA_BUCKET=${MEDIA_BUCKET},CLAIM_MODEL_ID=${MODEL_ID},SES_SENDER=${SES_SENDER},GUARDRAIL_ID=${GUARDRAIL_ID},GUARDRAIL_VERSION=${GUARDRAIL_VERSION}}"
if "$AWS" lambda get-function --region "$REGION" --function-name "$FUNC" >/dev/null 2>&1; then
  "$AWS" lambda update-function-code --region "$REGION" --function-name "$FUNC" \
    --zip-file "fileb://$BUILD/function.zip" >/dev/null
  sleep 3
  "$AWS" lambda update-function-configuration --region "$REGION" --function-name "$FUNC" \
    --environment "$ENV" --timeout 120 --memory-size 512 >/dev/null
  echo "   updated"
else
  "$AWS" lambda create-function --region "$REGION" --function-name "$FUNC" \
    --runtime "$PY" --handler lambda_function.lambda_handler \
    --role "$ROLE_ARN" --timeout 120 --memory-size 512 \
    --architectures "$ARCH" --environment "$ENV" \
    --zip-file "fileb://$BUILD/function.zip" >/dev/null
  echo "   created"
fi

echo "== 5. SQS event source mappings (RCS + WhatsApp) =="
wire_queue() {  # $1 = queue ARN  $2 = queue URL
  local qarn="$1" qurl="$2"
  # visibility timeout must be >= function timeout (120s)
  "$AWS" sqs set-queue-attributes --region "$REGION" --queue-url "$qurl" \
    --attributes VisibilityTimeout=130 >/dev/null 2>&1
  local existing
  existing=$("$AWS" lambda list-event-source-mappings --region "$REGION" --function-name "$FUNC" \
    --query "EventSourceMappings[?EventSourceArn=='${qarn}'].UUID" --output text 2>/dev/null)
  if [[ -z "$existing" || "$existing" == "None" ]]; then
    "$AWS" lambda create-event-source-mapping --region "$REGION" --function-name "$FUNC" \
      --event-source-arn "$qarn" --batch-size 1 >/dev/null && echo "   wired $qarn"
  else
    echo "   exists $qarn ($existing)"
  fi
}
wire_queue "$QUEUE_ARN" "https://sqs.us-east-1.amazonaws.com/${ACCOUNT}/cds-eum-events-debug"
wire_queue "$WA_QUEUE_ARN" "$WA_QUEUE_URL"

rm -rf "$BUILD"
echo "== done =="
echo "Logs: $AWS logs tail /aws/lambda/${FUNC} --follow --region ${REGION}"

#!/usr/bin/env bash
# Fill the ClaimPilot RCS testing registration fields, then submit.
set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWS="$DIR/../../scripts/awscds.sh"
REGION="us-east-1"

REG="registration-a99b0a59510a4770b1f541ac30b79f90"
LOGO_ATT="attachment-f4719148278e4240b21458eaa4b69242"
BANNER_ATT="attachment-ad0a6a323fb14a989405b26f861963ad"

set_text() {  # $1 = fieldPath  $2 = value
  "$AWS" pinpoint-sms-voice-v2 put-registration-field-value --region "$REGION" \
    --registration-id "$REG" --field-path "$1" --text-value "$2" >/dev/null \
    && echo "  set $1" || echo "  FAILED $1"
}
set_select() {  # $1 = fieldPath  $2 = selected choice
  "$AWS" pinpoint-sms-voice-v2 put-registration-field-value --region "$REGION" \
    --registration-id "$REG" --field-path "$1" --select-choices "$2" >/dev/null \
    && echo "  set $1=$2" || echo "  FAILED $1"
}
set_att() {  # $1 = fieldPath  $2 = attachmentId
  "$AWS" pinpoint-sms-voice-v2 put-registration-field-value --region "$REGION" \
    --registration-id "$REG" --field-path "$1" --registration-attachment-id "$2" >/dev/null \
    && echo "  set $1 (attachment)" || echo "  FAILED $1"
}

echo "== filling agentDetails =="
set_text   agentDetails.brandName          "ClaimPilot"
set_text   agentDetails.serviceName        "ClaimPilot Claims Assistant"
set_text   agentDetails.senderDisplayName  "ClaimPilot"
set_select agentDetails.useCase            "TRANSACTIONAL"
set_text   agentDetails.agentDescription   "ClaimPilot is an AI assistant that helps policyholders file and track insurance claims (First Notice of Loss) through a guided conversation."
set_att    agentDetails.logoImage          "$LOGO_ATT"
set_att    agentDetails.bannerImage        "$BANNER_ATT"
set_text   agentDetails.accentColor        "#1A56DB"
set_text   agentDetails.privacyPolicyUrl   "https://claimpilot.example.com/privacy"
set_text   agentDetails.termsAndConditionsUrl "https://claimpilot.example.com/terms"
set_select agentDetails.averageMonthlyRcsFrequency "10"
set_text   agentDetails.monthlyRcsVolume   "100"
set_select agentDetails.billingCategory    "CONVERSATIONAL"

echo "== current field values =="
"$AWS" pinpoint-sms-voice-v2 describe-registration-field-values --region "$REGION" \
  --registration-id "$REG" --query 'RegistrationFieldValues[].{field:FieldPath,text:TextValue,sel:SelectChoices,att:RegistrationAttachmentId}' --output table

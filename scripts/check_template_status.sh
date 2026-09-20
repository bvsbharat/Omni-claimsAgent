#!/usr/bin/env bash
# Poll WhatsApp template approval status.
# Usage: ./scripts/check_template_status.sh
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WABA="waba-26964a65f70442b2aa63f83f8a4404b1"
"$DIR/awscds.sh" socialmessaging list-whatsapp-message-templates \
  --id "$WABA" \
  --query 'templates[].{name:templateName,status:templateStatus,category:templateCategory,quality:templateQualityScore}' \
  --output table

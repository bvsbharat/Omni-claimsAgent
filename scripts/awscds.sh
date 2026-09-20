#!/usr/bin/env bash
#
# awscds.sh — reliable AWS CLI wrapper for the CDS hackathon.
#
# Why this exists:
#   1. The Homebrew `aws` (at /opt/homebrew/bin/aws) is broken on this machine —
#      its Python 3.14 `pyexpat` links against the system libexpat which is
#      missing a symbol, so every command crashes. We use the official standalone
#      AWS CLI v2 installed under ~/aws-cli instead.
#   2. Stale AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars in the shell
#      override the good `aws login` session credentials and cause
#      InvalidClientTokenId. We strip them here so the working credentials win.
#
# Usage:
#   ./scripts/awscds.sh sts get-caller-identity
#   ./scripts/awscds.sh pinpoint-sms-voice-v2 describe-phone-numbers
#
# Default region is us-east-1 (where all CDS resources live).

AWS_BIN="/Users/bharatbvs/aws-cli/aws-cli/aws"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

exec env \
  -u AWS_ACCESS_KEY_ID \
  -u AWS_SECRET_ACCESS_KEY \
  -u AWS_SESSION_TOKEN \
  "$AWS_BIN" "$@"

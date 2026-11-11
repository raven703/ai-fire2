#!/bin/sh
set -eu
cd /home/user/ai-fire2
if [ -e .env ]; then echo '.env already exists; not overwriting'; exit 1; fi
umask 077
for name in USER_KEY USER_B_KEY VAULT_KEY ADMISSION_KEY STORE_KEY LITELLM_KEY MOCK_KEY TEST_KEY WEBUI_SECRET_KEY; do
  prefix=''
  if [ "$name" = LITELLM_KEY ]; then prefix='sk-'; fi
  printf '%s=%s%s\n' "$name" "$prefix" "$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
done > .env
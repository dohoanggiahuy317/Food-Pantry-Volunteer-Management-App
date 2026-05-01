#!/usr/bin/env bash
# VM-101 Component Tests — Demo Runner
#
# Usage:
#   ./run_component_tests_demo.sh              # run all component tests
#   ./run_component_tests_demo.sh -k auth      # run only auth component tests
#   ./run_component_tests_demo.sh -k db        # run only DB component tests
#   ./run_component_tests_demo.sh -k notif     # run only notifications tests
#
# Prerequisites:
#   - Docker running locally
#   - Python venv activated (or dependencies installed in PATH)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$ROOT/docker-compose.test.yml"
ENV_FILE="$ROOT/.env.test"

# ── Colour output ──────────────────────────────────────────────────────────────
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
RESET="\033[0m"
SEP="════════════════════════════════════════════════"

echo -e "\n${BOLD}${CYAN}${SEP}${RESET}"
echo -e "${BOLD}${CYAN}  VM-101 Component Tests — Demo Run${RESET}"
echo -e "${BOLD}${CYAN}${SEP}${RESET}\n"

# ── Step 1: Verify .env.test exists ───────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Cannot run component tests without it."
  exit 1
fi

# ── Step 2: Start test MySQL ───────────────────────────────────────────────────
echo -e "[1/4] ${BOLD}Starting test MySQL container...${RESET}"
docker compose -f "$COMPOSE_FILE" up -d --wait
echo -e "      ${GREEN}Container healthy.${RESET}\n"

# ── Step 3: Load .env.test ────────────────────────────────────────────────────
echo -e "[2/4] ${BOLD}Loading .env.test environment...${RESET}"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
echo -e "      ${GREEN}Done.${RESET}\n"

# ── Step 4: Run component tests ───────────────────────────────────────────────
echo -e "[3/4] ${BOLD}Running component tests...${RESET}"
echo -e "      ${SEP}"

EXIT_CODE=0
python -m pytest "$ROOT/tests/component/" \
    --override-ini="addopts=" \
    -v \
    --tb=short \
    -m component \
    --cov=backend \
    --cov-report=term-missing \
    --cov-report=html:"$ROOT/htmlcov/component" \
    "$@" || EXIT_CODE=$?

# ── Step 5: Tear down ──────────────────────────────────────────────────────────
echo ""
echo -e "[4/4] ${BOLD}Stopping test MySQL container...${RESET}"
docker compose -f "$COMPOSE_FILE" down
echo -e "      ${GREEN}Container stopped.${RESET}"

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}${CYAN}${SEP}${RESET}"
if [[ $EXIT_CODE -eq 0 ]]; then
  echo -e "${BOLD}${GREEN}  All component tests passed.${RESET}"
else
  echo -e "\033[31m${BOLD}  Some tests failed (exit code $EXIT_CODE).${RESET}"
fi
echo -e "${BOLD}${CYAN}  Coverage report: htmlcov/component/index.html${RESET}"
echo -e "${BOLD}${CYAN}${SEP}${RESET}\n"

exit $EXIT_CODE

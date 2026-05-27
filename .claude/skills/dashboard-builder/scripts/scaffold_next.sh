#!/usr/bin/env bash
# Scaffold a Next.js 15 + shadcn/ui + Tremor + Recharts dashboard project.
# Usage: bash scaffold_next.sh <project-name>

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <project-name>" >&2
  exit 2
fi

NAME="$1"

echo "==> Creating Next.js app: $NAME"
npx --yes create-next-app@latest "$NAME" \
  --typescript --tailwind --app --src-dir --import-alias "@/*" --use-npm --no-eslint --turbo

cd "$NAME"

echo "==> Initialising shadcn/ui"
npx --yes shadcn@latest init -d --base-color zinc

echo "==> Adding shadcn components"
npx --yes shadcn@latest add \
  button card dialog sheet dropdown-menu input table tabs badge \
  separator sonner command chart tooltip select skeleton

echo "==> Installing chart + utility libs"
npm install @tremor/react recharts lucide-react motion nuqs vaul date-fns clsx

echo "==> Done."
echo
echo "Next steps:"
echo "  cd $NAME"
echo "  npm run dev    # http://localhost:3000"
echo
echo "Recommended files to create:"
echo "  src/components/tiles/kpi-tile.tsx"
echo "  src/components/tiles/trend-tile.tsx"
echo "  src/components/filter-bar.tsx"
echo "  src/lib/format.ts"
echo
echo "See modes/next-shadcn/README.md for layout + theming guidance."

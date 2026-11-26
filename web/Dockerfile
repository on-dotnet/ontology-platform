# Web app images. Targets used by dev.ps1 / compose.yaml: lock, test, runtime, e2e.

# Only the e2e stage uses it. ./dev.ps1 e2e passes the exact @playwright/test version from
# package.json (via compose), so the image's browsers always match the installed test runner.
ARG PLAYWRIGHT_VERSION

FROM node:24-alpine AS base
ARG NPM_REGISTRY=https://registry.npmjs.org
ENV CI=true
RUN npm install --global --no-fund --no-audit --registry="$NPM_REGISTRY" pnpm@11.28.8 \
  && pnpm config set registry "$NPM_REGISTRY" \
  && node --version && pnpm --version
WORKDIR /app

# Resolves dependencies and writes /app/pnpm-lock.yaml (fetched by `./dev.ps1 lock web`).
FROM base AS lock
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
RUN pnpm install --lockfile-only

FROM base AS deps
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
RUN --mount=type=cache,id=ontology-web-pnpm-store,target=/pnpm/store \
  pnpm install --frozen-lockfile --store-dir /pnpm/store

# Lint, typecheck and unit tests (`./dev.ps1 test-web`).
FROM deps AS test
COPY . .
RUN pnpm run routes
CMD ["sh", "scripts/check.sh"]

# End-to-end smoke tests (`./dev.ps1 e2e`). The official Playwright image carries the browsers, so
# they stay out of the repository; the test runner and its dependencies are plain JavaScript and
# come from the deps stage.
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble AS e2e
ARG PLAYWRIGHT_VERSION
ENV CI=true
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY package.json playwright.config.ts tsconfig.e2e.json ./
COPY e2e ./e2e
# Guards against a lockfile that resolved another version than package.json names.
RUN installed="$(node -p "require('./node_modules/@playwright/test/package.json').version")" \
  && { [ "$installed" = "$PLAYWRIGHT_VERSION" ] || { echo "@playwright/test $installed does not match the image v$PLAYWRIGHT_VERSION; run ./dev.ps1 lock web"; exit 1; }; }
CMD ["node_modules/.bin/playwright", "test"]

FROM deps AS build
COPY . .
RUN pnpm run build

# Runs as uid 101 (nginx); pid and temp paths live in /tmp, set by the image's nginx.conf.
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/api-proxy.conf nginx/headers-common.conf nginx/headers-app.conf nginx/headers-api.conf /etc/nginx/snippets/
COPY --from=build /app/dist /usr/share/nginx/html
# Fail the build on an invalid config, and confirm the non-root runtime settings this image relies on.
RUN nginx -t \
  && [ "$(id -u)" != "0" ] \
  && nginx -T 2>/dev/null | grep -Eq '^pid +/tmp/' \
  && nginx -T 2>/dev/null | grep -Eq 'proxy_temp_path +/tmp/' \
  && [ -w /tmp ]
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

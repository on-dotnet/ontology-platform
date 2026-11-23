# Web app images. Targets used by dev.ps1 / compose.yaml: lock, test, runtime.

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

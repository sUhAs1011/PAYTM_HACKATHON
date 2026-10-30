# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund

FROM node:22-bookworm-slim AS runtime
WORKDIR /app
COPY --from=deps --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . .
# Writable Angular CLI / Vite cache for the non-root dev server (WORKDIR /app
# is root-owned; ng serve writes .angular/cache at runtime).
RUN mkdir -p .angular/cache && chown -R node:node .angular
USER node
EXPOSE 4200
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--port", "4200", "--proxy-config", "proxy.docker.conf.json"]

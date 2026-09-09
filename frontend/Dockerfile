# syntax=docker/dockerfile:1

# ---- Stage 1: build the SPA ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Stage 2: serve with Caddy ----
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80

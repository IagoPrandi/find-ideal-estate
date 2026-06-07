# Stage 1 — build do React app
FROM node:20-alpine AS build-web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
ARG VITE_API_BASE
ARG VITE_MAPTILER_API_KEY
RUN npm run build

# Stage 2 — build do Astro SSG
FROM node:20-alpine AS build-content
WORKDIR /content
COPY apps/content/package*.json ./
RUN npm ci
COPY apps/content ./
RUN npm run build

# Stage 3 — nginx servindo os dois builds no mesmo container
FROM nginx:alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build-web /web/dist /usr/share/nginx/html/web
COPY --from=build-content /content/dist /usr/share/nginx/html/content
EXPOSE 80

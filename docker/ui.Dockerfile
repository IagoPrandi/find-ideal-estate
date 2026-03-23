FROM node:20-alpine
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
EXPOSE 5173

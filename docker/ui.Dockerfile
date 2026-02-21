FROM node:20-alpine
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci
COPY ui ./
EXPOSE 5173

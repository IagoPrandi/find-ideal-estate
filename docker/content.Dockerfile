FROM node:22-alpine
WORKDIR /content
COPY apps/content/package*.json ./
RUN npm ci
COPY apps/content ./
EXPOSE 4321
